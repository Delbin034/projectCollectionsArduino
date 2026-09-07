#include <SPI.h>
#include <MFRC522.h>
#include <Servo.h>

// =======================================================
// FLOOD RELIEF CAMP - RFID CHECK-IN KIOSK FIRMWARE
//
// Reads RFID cards and reports the UID to the Python GUI.
// The GUI decides what happened (new registration, check-in,
// check-out, duplicate, unknown card, priority/vulnerable
// case, camp at capacity) and tells this board how to
// respond via buzzer / entry gate servo.
//
// The gate servo only moves for VALID outcomes (a
// recognized card being registered, checked in, or
// checked out). It stays at its resting/closed position
// for anything invalid (unknown card, duplicate, or a
// capacity warning).
// =======================================================

// -------------------------------
// PIN CONFIGURATION
// -------------------------------
#define SS_PIN       7
#define RST_PIN       9

#define BUZZER_PIN    8

#define SERVO_PIN     6

#define GATE_CLOSED  60
#define GATE_OPEN   170

MFRC522 rfid(SS_PIN, RST_PIN);
Servo gateServo;

// Used to avoid reading the same card continuously
String lastUID = "";
unsigned long lastScanTime = 0;

void setup() {

  Serial.begin(9600);

  SPI.begin();
  rfid.PCD_Init();

  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  gateServo.attach(SERVO_PIN);
  gateServo.write(GATE_CLOSED);

  Serial.println("Relief Camp Check-In System");
  Serial.println("READY");
}

void loop() {

  checkRFID();
  checkPythonResponse();
}


// =======================================================
// RFID SCANNING
// =======================================================

void checkRFID() {

  if (!rfid.PICC_IsNewCardPresent())
    return;

  if (!rfid.PICC_ReadCardSerial())
    return;

  String uid = "";

  for (byte i = 0; i < rfid.uid.size; i++) {

    if (rfid.uid.uidByte[i] < 0x10)
      uid += "0";

    uid += String(rfid.uid.uidByte[i], HEX);
  }

  uid.toUpperCase();

  // Prevent repeated reading of the same card
  if (uid == lastUID && millis() - lastScanTime < 2000) {

    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();

    return;
  }

  lastUID = uid;
  lastScanTime = millis();

  Serial.println("Card Scanned - Checking...");

  Serial.print("CARD:");
  Serial.println(uid);

  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
}


// =======================================================
// RECEIVE COMMANDS FROM PYTHON
// =======================================================

void checkPythonResponse() {

  if (!Serial.available())
    return;

  String message = Serial.readStringUntil('\n');
  message.trim();

  String type = message;
  String value = "";

  int sep = message.indexOf('|');

  if (sep > 0) {
    type = message.substring(0, sep);
    value = message.substring(sep + 1);
  }

  if (type == "REGISTERED") {
    cardRegistered(value);

  } else if (type == "REGISTEREDPRIORITY") {
    cardRegisteredPriority(value);

  } else if (type == "EXISTS") {
    cardExists(value);

  } else if (type == "CHECKIN") {
    cardCheckin(value);

  } else if (type == "CHECKINPRIORITY") {
    cardCheckinPriority(value);

  } else if (type == "CHECKOUT") {
    cardCheckout(value);

  } else if (type == "UNKNOWN") {
    cardUnknown(value);

  } else if (type == "CAMPFULL") {
    campFull(value);
  }
}


// =======================================================
// EVENT RESPONSES
// =======================================================

void cardRegistered(String name) {

  Serial.print("Registered: ");
  Serial.println(name);

  beep(1, 150);
  openGate();
}

void cardRegisteredPriority(String name) {

  Serial.print("Registered PRIORITY CASE: ");
  Serial.println(name);

  beep(2, 150);
  openGate();
}

void cardExists(String name) {

  Serial.println("Already Registered");

  beep(2, 120);
  delay(800);
}

void cardCheckin(String name) {

  Serial.print("Checked In: ");
  Serial.println(name);

  beep(1, 150);
  openGate();
}

void cardCheckinPriority(String name) {

  Serial.print("IN - PRIORITY: ");
  Serial.println(name);

  beep(2, 150);
  openGate();
}

void cardCheckout(String name) {

  Serial.print("Checked Out: ");
  Serial.println(name);

  beep(1, 150);
  openGate();
}

void cardUnknown(String uid) {

  Serial.println("Unknown Card - Not Registered");

  beep(3, 100);
  delay(800);
}

void campFull(String name) {

  Serial.println("CAMP AT / OVER CAPACITY!");

  digitalWrite(BUZZER_PIN, HIGH);
  delay(600);
  digitalWrite(BUZZER_PIN, LOW);

  delay(1000);
}


// =======================================================
// BUZZER HELPER
// =======================================================

void beep(int times, int ms) {

  for (int i = 0; i < times; i++) {
    digitalWrite(BUZZER_PIN, HIGH);
    delay(ms);
    digitalWrite(BUZZER_PIN, LOW);
    delay(ms);
  }
}

void openGate() {

  gateServo.write(GATE_OPEN);
  delay(2500);
  gateServo.write(GATE_CLOSED);
}