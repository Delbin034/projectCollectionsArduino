#include <Wire.h>
#include <SoftwareSerial.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <LiquidCrystal_I2C.h>

// =====================================================
// PIN CONFIGURATION
// =====================================================

#define TRIG_PIN 5
#define ECHO_PIN 4

// -------------------------------
// GSM module - moved to SoftwareSerial so AT commands
// and Serial Monitor debug output no longer share the
// same line (the Uno has only one hardware UART, which
// is also used by USB). This mirrors the working GSM
// test sketch: SIM900A TX -> Arduino pin 7,
// SIM900A RX -> Arduino pin 6 (through a voltage
// divider / level shifter - SIM900A RX is not 5V safe
// long-term).
// -------------------------------
SoftwareSerial gsm(6, 7); // RX, TX

#define WATER_SENSOR A0

// -------------------------------
// I2C LCD
// Shares the same I2C bus as the MPU6050 - no extra
// pins needed. On the Arduino Uno, I2C is fixed at:
//   SDA -> A4
//   SCL -> A5
// Change the address below to 0x3F if 0x27 shows
// nothing (the two most common backpack addresses).
// -------------------------------
LiquidCrystal_I2C lcd(0x27, 16, 2);

// -------------------------------
// STATUS LEDs + BUZZER
// One LED per alert level, buzzer
// sounds only for the HIGH alert
// -------------------------------
#define LED_LOW_PIN      9
#define LED_MEDIUM_PIN  10
#define LED_HIGH_PIN    11
#define BUZZER_PIN      12

// =====================================================
// MPU6050
// =====================================================

Adafruit_MPU6050 mpu;

// =====================================================
// REGISTERED ALERT PHONE NUMBERS
//
// REQUIRED FORMAT: "+91" followed by exactly 10 digits,
// no spaces, no dashes, no leading 0.
// Example: "+919876543210"  (+91 + 10 digits = 13 chars)
//
// The "ERROR" you saw from the module happens when a
// number does NOT match this format - e.g. missing the
// +91 prefix or having the wrong digit count. Replace
// BOTH placeholders below with your real numbers before
// uploading.
// =====================================================

String alertNumbers[] = {
  "+91xxxxxxxxxx",   // <-- REPLACE with real 13-char number
  "+91xxxxxxxxxx"    // <-- REPLACE with real 13-char number
};

int numAlertNumbers = sizeof(alertNumbers) / sizeof(alertNumbers[0]);

// Delay between sending to consecutive numbers so the
// SIM900A has time to finish one SMS before the next
#define SMS_SEND_GAP_MS 4000

// =====================================================
// THRESHOLDS
// =====================================================

// Ultrasonic distance in cm
#define HIGH_WATER_CM       7.0
#define MEDIUM_WATER_CM    10.0

// Water sensor ADC
// Adjust after calibration
#define WATER_HIGH_ADC      700
#define WATER_MEDIUM_ADC    500
#define WATER_LOW_ADC       300

// MPU vibration threshold
// Adjust according to installation
#define VIBRATION_HIGH      3.0
#define VIBRATION_MEDIUM    1.5

// =====================================================
// ALERT LEVEL CLASSIFICATION
//
// IMPORTANT: this uses OR logic - ANY ONE sensor
// crossing its threshold is enough to raise the level.
// Checked in priority order: HIGH first, then MEDIUM,
// otherwise LOW. This one function is used by the LEDs,
// the LCD, and the SMS alerts, so all three can never
// disagree with each other.
// =====================================================

enum AlertLevel {
  LEVEL_LOW,
  LEVEL_MEDIUM,
  LEVEL_HIGH
};

AlertLevel classifyAlertLevel(
  float distance,
  int waterADC,
  float vibration
)
{
  bool high = (
    distance < HIGH_WATER_CM ||
    waterADC >= WATER_HIGH_ADC ||
    vibration >= VIBRATION_HIGH
  );

  if (high) {
    return LEVEL_HIGH;
  }

  bool medium = (
    distance <= MEDIUM_WATER_CM ||
    waterADC >= WATER_MEDIUM_ADC ||
    vibration >= VIBRATION_MEDIUM
  );

  if (medium) {
    return LEVEL_MEDIUM;
  }

  return LEVEL_LOW;
}

// =====================================================
// SMS LATCH
// Only HIGH and MEDIUM latches remain - LOW never
// sends an SMS, so it needs no latch.
// =====================================================

bool highAlertSent = false;
bool mediumAlertSent = false;

// =====================================================
// SETUP
// =====================================================

void setup()
{
  Serial.begin(9600);

  gsm.begin(9600);

  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  pinMode(WATER_SENSOR, INPUT);

  pinMode(LED_LOW_PIN, OUTPUT);
  pinMode(LED_MEDIUM_PIN, OUTPUT);
  pinMode(LED_HIGH_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);

  digitalWrite(LED_LOW_PIN, LOW);
  digitalWrite(LED_MEDIUM_PIN, LOW);
  digitalWrite(LED_HIGH_PIN, LOW);
  digitalWrite(BUZZER_PIN, LOW);

  Wire.begin();

  lcd.init();
  lcd.backlight();

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Flood Alert Sys");
  lcd.setCursor(0, 1);
  lcd.print("Starting...");

  // ---------------------------------------------
  // MPU6050
  // ---------------------------------------------

  if (!mpu.begin())
  {
    Serial.println(F("MPU6050 NOT FOUND!"));
    while (1)
    {
      delay(1000);
    }
  }
  Serial.println(F("MPU6050 OK"));
  mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
  mpu.setGyroRange(MPU6050_RANGE_500_DEG);

  // ---------------------------------------------
  // SIM900A initialization
  // ---------------------------------------------
  delay(3000);

  gsm.println(F("AT"));
  delay(1000);

  gsm.println(F("ATE0"));
  delay(500);

  gsm.println(F("AT+CMGF=1"));
  delay(500);

  Serial.println(F("Flood Alert System Ready"));

  Serial.println(F("--------------------------------"));
  Serial.println(F("GSM Serial: SoftwareSerial on pins 7(RX)/6(TX)"));
  Serial.println(F("SMS policy: sent for HIGH and MEDIUM alerts only"));

  Serial.println(F("Registered Alert Numbers:"));

  for (int i = 0; i < numAlertNumbers; i++)
  {
    Serial.print(F("  "));
    Serial.print(i + 1);
    Serial.print(F(". "));
    Serial.print(alertNumbers[i]);

    // Basic sanity check so a malformed number is
    // caught here in the Serial log instead of only
    // showing up later as a confusing modem ERROR.
    if (!isValidNumber(alertNumbers[i]))
    {
      Serial.print(F("   <-- INVALID FORMAT! Expected +91 plus 10 digits (13 chars total)"));
    }

    Serial.println();
  }

  Serial.println(F("--------------------------------"));
}

// =====================================================
// VALIDATE PHONE NUMBER FORMAT
// Expects "+91" followed by exactly 10 digits (13 chars
// total). Does not guarantee the number is real/active,
// only that its format won't cause an immediate modem
// ERROR.
// =====================================================

bool isValidNumber(String number)
{
  if (number.length() != 13)
  {
    return false;
  }

  if (!number.startsWith("+91"))
  {
    return false;
  }

  for (int i = 3; i < 13; i++)
  {
    if (!isDigit(number.charAt(i)))
    {
      return false;
    }
  }

  return true;
}

// =====================================================
// MAIN LOOP
// =====================================================

void loop()
{
  // ---------------------------------------------
  // Read sensors
  // ---------------------------------------------

  float distance = readUltrasonic();
  int waterADC = readWaterSensor();
  float vibration = readVibration();

  // ---------------------------------------------
  // Classify current level once - LEDs, LCD, and
  // the SMS alerts below all use this same result
  // ---------------------------------------------

  AlertLevel level = classifyAlertLevel(
    distance,
    waterADC,
    vibration
  );

  // ---------------------------------------------
  // Update status LEDs / buzzer - always reflects
  // the current live reading, independent of the
  // SMS "send once" latches below
  // ---------------------------------------------

  updateStatusIndicators(level);

  // ---------------------------------------------
  // Convert water sensor to percentage
  // ---------------------------------------------

  int waterPercent = map(
    waterADC,
    0,
    1023,
    0,
    100
  );

  waterPercent = constrain(
    waterPercent,
    0,
    100
  );

  // ---------------------------------------------
  // Display sensor data
  // ---------------------------------------------

  Serial.println();
  Serial.println(F("========== SENSOR DATA =========="));

  Serial.print(F("Water Distance : "));
  Serial.print(distance);
  Serial.println(F(" cm"));

  Serial.print(F("Water Sensor   : "));
  Serial.print(waterADC);
  Serial.print(F(" ("));
  Serial.print(waterPercent);
  Serial.println(F("%)"));

  Serial.print(F("Vibration      : "));
  Serial.println(vibration);

  updateLCD(
    level,
    distance,
    waterPercent
  );

  // ---------------------------------------------
  // SMS ALERTS - only HIGH and MEDIUM trigger SMS,
  // each sent once per level (latched). LOW never
  // sends an SMS and resets both latches so a fresh
  // HIGH/MEDIUM after recovering to LOW will alert
  // again.
  // ---------------------------------------------

  switch (level)
  {
    case LEVEL_HIGH:

      Serial.println(F("RED ALERT CONDITION!"));

      if (!highAlertSent)
      {
        sendHighAlert(
          distance,
          waterPercent,
          vibration
        );

        highAlertSent = true;
      }

      break;

    case LEVEL_MEDIUM:

      Serial.println(F("MEDIUM LEVEL"));

      if (!mediumAlertSent)
      {
        sendMediumAlert(
          distance,
          waterPercent,
          vibration
        );

        mediumAlertSent = true;
      }

      break;

    case LEVEL_LOW:
    default:

      Serial.println(F("LOW LEVEL - no SMS sent"));

      // Reset latches once the system returns to LOW,
      // so the next time it rises to MEDIUM or HIGH it
      // sends a fresh alert instead of staying silent.
      highAlertSent = false;
      mediumAlertSent = false;

      break;
  }

  delay(2000);
}


// =====================================================
// WATER SENSOR
//
// On this sensor/wiring, the raw ADC reads HIGH when
// dry and LOW when wet - inverted here once so all
// downstream logic treats a HIGHER value as MORE water.
// =====================================================

int readWaterSensor()
{
  int rawADC = analogRead(WATER_SENSOR);
  int invertedADC = 1023 - rawADC;
  return invertedADC;
}


// =====================================================
// ULTRASONIC DISTANCE
// =====================================================

float readUltrasonic()
{
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);

  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);

  digitalWrite(TRIG_PIN, LOW);

  long duration = pulseIn(
    ECHO_PIN,
    HIGH,
    30000
  );

  if (duration == 0)
  {
    return 999.0;
  }

  float distance = duration * 0.0343 / 2.0;

  return distance;
}


// =====================================================
// MPU6050 VIBRATION
// =====================================================

float readVibration()
{
  sensors_event_t accel;
  sensors_event_t gyro;
  sensors_event_t temp;

  mpu.getEvent(
    &accel,
    &gyro,
    &temp
  );

  float magnitude = sqrt(
    accel.acceleration.x * accel.acceleration.x +
    accel.acceleration.y * accel.acceleration.y +
    accel.acceleration.z * accel.acceleration.z
  );

  float vibration = abs(magnitude - 9.81);

  return vibration;
}


// =====================================================
// STATUS LEDS / BUZZER
// =====================================================

void updateStatusIndicators(AlertLevel level)
{
  digitalWrite(LED_HIGH_PIN, level == LEVEL_HIGH ? HIGH : LOW);
  digitalWrite(LED_MEDIUM_PIN, level == LEVEL_MEDIUM ? HIGH : LOW);
  digitalWrite(LED_LOW_PIN, level == LEVEL_LOW ? HIGH : LOW);

  if (level == LEVEL_HIGH)
  {
    soundHighAlertBuzzer();
  }
  else
  {
    digitalWrite(BUZZER_PIN, LOW);
  }
}


// =====================================================
// HIGH ALERT BUZZER
//
// Beeps for up to 10 seconds, re-checking sensors every
// half-second so it can stop early if level drops.
// =====================================================

void soundHighAlertBuzzer()
{
  Serial.println(F("HIGH ALERT - buzzer on (up to 10s)"));

  const unsigned long BUZZ_DURATION_MS = 10000;
  const unsigned long BEEP_ON_MS = 250;
  const unsigned long BEEP_OFF_MS = 250;

  unsigned long startTime = millis();

  while (millis() - startTime < BUZZ_DURATION_MS)
  {
    digitalWrite(BUZZER_PIN, HIGH);
    delay(BEEP_ON_MS);
    digitalWrite(BUZZER_PIN, LOW);
    delay(BEEP_OFF_MS);

    float currentDistance = readUltrasonic();
    int currentWaterADC = readWaterSensor();
    float currentVibration = readVibration();

    AlertLevel currentLevel = classifyAlertLevel(
      currentDistance,
      currentWaterADC,
      currentVibration
    );

    if (currentLevel != LEVEL_HIGH)
    {
      Serial.println(F("Level dropped out of HIGH - alarm stopped early"));
      break;
    }
  }

  digitalWrite(BUZZER_PIN, LOW);
}


// =====================================================
// LCD DISPLAY
// =====================================================

void updateLCD(
  AlertLevel level,
  float distance,
  int waterPercent
)
{
  String levelText;

  switch (level)
  {
    case LEVEL_HIGH:
      levelText = "STATUS: HIGH!";
      break;

    case LEVEL_MEDIUM:
      levelText = "STATUS: MEDIUM";
      break;

    default:
      levelText = "STATUS: LOW";
      break;
  }

  lcd.clear();

  lcd.setCursor(0, 0);
  lcd.print("D:");
  lcd.print(distance, 1);
  lcd.print("cm W:");
  lcd.print(waterPercent);
  lcd.print("%");

  lcd.setCursor(0, 1);
  lcd.print(levelText);
}


// =====================================================
// SEND HIGH ALERT
// =====================================================

void sendHighAlert(
  float distance,
  int waterPercent,
  float vibration
)
{
  Serial.println(F("Sending RED ALERT SMS to all registered numbers..."));

  String message = "";

  message += F("RED FLOOD ALERT! ");
  message += F("Water Level HIGH. ");
  message += F("Distance: ");
  message += String(distance, 1);
  message += F(" cm. ");

  message += F("Water Sensor: ");
  message += String(waterPercent);
  message += F("%. ");

  message += F("Vibration: HIGH. ");

  message += F("Immediate Action Required!");

  sendSMSToAll(message);
}


// =====================================================
// SEND MEDIUM ALERT
// =====================================================

void sendMediumAlert(
  float distance,
  int waterPercent,
  float vibration
)
{
  Serial.println(F("Sending MEDIUM ALERT SMS to all registered numbers..."));

  String message = "";

  message += F("MEDIUM FLOOD ALERT. ");
  message += F("Water Level: MEDIUM. ");

  message += F("Distance: ");
  message += String(distance, 1);
  message += F(" cm. ");

  message += F("Water: ");
  message += String(waterPercent);
  message += F("%. ");

  message += F("Vibration: LOW/MEDIUM. ");

  message += F("Monitor Water Level.");

  sendSMSToAll(message);
}


// =====================================================
// SEND SMS TO EVERY REGISTERED NUMBER
// =====================================================

void sendSMSToAll(String message)
{
  for (int i = 0; i < numAlertNumbers; i++)
  {
    Serial.print(F("Sending to number "));
    Serial.print(i + 1);
    Serial.print(F(" of "));
    Serial.print(numAlertNumbers);
    Serial.print(F(" ("));
    Serial.print(alertNumbers[i]);
    Serial.println(F(")..."));

    sendSMS(
      alertNumbers[i],
      message
    );

    if (i < numAlertNumbers - 1)
    {
      delay(SMS_SEND_GAP_MS);
    }
  }

  Serial.println(F("Finished sending to all registered numbers."));
}


// =====================================================
// SEND SMS TO A SINGLE NUMBER
// =====================================================

void sendSMS(
  String number,
  String message
)
{
  // Skip numbers that are the wrong format up front -
  // this is what was previously producing a modem
  // ERROR and then letting the message text/Ctrl+Z get
  // sent anyway as stray bytes, generating the extra
  // spurious OKs seen in the log.
  if (!isValidNumber(number))
  {
    Serial.print(F("Skipping invalid number: "));
    Serial.println(number);
    return;
  }

  Serial.println(F("Initializing SMS..."));

  gsm.println(F("AT+CMGF=1"));
  delay(1000);
  flushGsmResponse();

  gsm.print(F("AT+CMGS=\""));
  gsm.print(number);
  gsm.println(F("\""));

  // Wait for the '>' prompt the module sends before it
  // will accept message text. If the number/command was
  // rejected, this will time out instead of blindly
  // sending message text into a dead command.
  if (!waitForPrompt(3000))
  {
    Serial.println(F("No '>' prompt received - aborting this SMS (check number/module)."));
    flushGsmResponse();
    return;
  }

  gsm.print(message);
  delay(500);

  gsm.write(26); // CTRL+Z

  delay(5000);

  Serial.println(F("SMS command completed."));

  flushGsmResponse();
}

// =====================================================
// WAIT FOR '>' PROMPT
// Returns true if '>' is seen within timeoutMs,
// false otherwise. Echoes bytes to Serial as they
// arrive for visibility.
// =====================================================

bool waitForPrompt(unsigned long timeoutMs)
{
  unsigned long start = millis();

  while (millis() - start < timeoutMs)
  {
    if (gsm.available())
    {
      char c = gsm.read();
      Serial.write(c);

      if (c == '>')
      {
        return true;
      }
    }
  }

  return false;
}

// =====================================================
// FLUSH / PRINT ANY PENDING GSM RESPONSE
// =====================================================

void flushGsmResponse()
{
  delay(200);

  while (gsm.available())
  {
    Serial.write(
      gsm.read()
    );
  }
}
