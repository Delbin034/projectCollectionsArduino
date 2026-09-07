import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import serial
import serial.tools.list_ports
import threading
import queue
import os
import csv
from datetime import datetime


# =====================================================
# CONFIGURATION
# =====================================================

BAUD_RATE = 9600

DATABASE_FILE = "camp_people.csv"
LOG_FILE = "checkin_log.csv"

PEOPLE_FIELDS = [
    "uid", "name", "age", "gender", "family_id", "phone",
    "zone", "special_needs", "status",
    "registered_date", "last_checkin", "last_checkout"
]

SPECIAL_NEEDS_OPTIONS = [
    "Elderly", "Child", "Medical", "Pregnant", "Disabled"
]

DEFAULT_CAPACITY = 200


# =====================================================
# MAIN APPLICATION
# =====================================================

class CampRegistrationApp:

    def __init__(self, root):

        self.root = root
        self.root.title(
            "Flood Relief Camp - RFID Registration & Check-In System"
        )
        self.root.geometry("1080x780")

        self.serial_connection = None
        self.serial_thread = None
        self.running = False

        # mode is one of: "register", "checkinout", "dashboard"
        self.mode = "register"

        self.awaiting_registration = False

        self.data_queue = queue.Queue()

        self.ensure_files()

        self.create_widgets()

        self.refresh_ports()
        self.refresh_dashboard()

        self.root.after(100, self.process_serial_queue)

        self.root.protocol(
            "WM_DELETE_WINDOW",
            self.close_application
        )


    # =================================================
    # FILE SETUP
    # =================================================

    def ensure_files(self):

        if not os.path.exists(DATABASE_FILE):

            with open(
                DATABASE_FILE, "w", newline="", encoding="utf-8"
            ) as f:

                writer = csv.DictWriter(f, fieldnames=PEOPLE_FIELDS)
                writer.writeheader()

        if not os.path.exists(LOG_FILE):

            with open(
                LOG_FILE, "w", newline="", encoding="utf-8"
            ) as f:

                writer = csv.writer(f)
                writer.writerow(["timestamp", "uid", "name", "action"])


    # =================================================
    # DATA ACCESS (CSV based people registry)
    # =================================================

    def load_people(self):

        people = []

        with open(
            DATABASE_FILE, "r", newline="", encoding="utf-8"
        ) as f:

            reader = csv.DictReader(f)

            for row in reader:
                people.append(row)

        return people

    def save_people(self, people):

        with open(
            DATABASE_FILE, "w", newline="", encoding="utf-8"
        ) as f:

            writer = csv.DictWriter(f, fieldnames=PEOPLE_FIELDS)
            writer.writeheader()

            for p in people:
                writer.writerow(p)

    def find_person(self, uid):

        for p in self.load_people():

            if p["uid"].upper() == uid.upper():
                return p

        return None

    def upsert_person(self, person):

        people = self.load_people()

        updated = False

        for i, p in enumerate(people):

            if p["uid"].upper() == person["uid"].upper():
                people[i] = person
                updated = True
                break

        if not updated:
            people.append(person)

        self.save_people(people)

    def append_checkin_log(self, uid, name, action):

        with open(
            LOG_FILE, "a", newline="", encoding="utf-8"
        ) as f:

            writer = csv.writer(f)

            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                uid,
                name,
                action
            ])


    # =================================================
    # GUI CONSTRUCTION
    # =================================================

    def create_widgets(self):

        title = tk.Label(
            self.root,
            text="FLOOD RELIEF CAMP - RFID CHECK-IN SYSTEM",
            font=("Arial", 18, "bold")
        )

        title.pack(pady=8)

        self.create_connection_frame()

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=15, pady=5)

        self.register_tab = ttk.Frame(self.notebook)
        self.checkinout_tab = ttk.Frame(self.notebook)
        self.dashboard_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.register_tab, text="Register New Person")
        self.notebook.add(self.checkinout_tab, text="Check-In / Check-Out")
        self.notebook.add(self.dashboard_tab, text="Camp Dashboard & Search")

        self.notebook.bind(
            "<<NotebookTabChanged>>",
            self.on_tab_changed
        )

        self.create_register_tab()
        self.create_checkinout_tab()
        self.create_dashboard_tab()

        self.create_log_frame()


    # -------------------------------------------------
    # CONNECTION FRAME
    # -------------------------------------------------

    def create_connection_frame(self):

        serial_frame = ttk.LabelFrame(
            self.root,
            text="Arduino Connection"
        )

        serial_frame.pack(fill="x", padx=15, pady=5)

        ttk.Label(serial_frame, text="COM Port:").grid(
            row=0, column=0, padx=5, pady=10
        )

        self.port_combo = ttk.Combobox(
            serial_frame, width=15, state="readonly"
        )

        self.port_combo.grid(row=0, column=1, padx=5)

        ttk.Button(
            serial_frame, text="Refresh", command=self.refresh_ports
        ).grid(row=0, column=2, padx=5)

        self.connect_button = ttk.Button(
            serial_frame, text="Connect", command=self.connect_arduino
        )

        self.connect_button.grid(row=0, column=3, padx=5)

        self.connection_label = tk.Label(
            serial_frame, text="Disconnected", fg="red",
            font=("Arial", 10, "bold")
        )

        self.connection_label.grid(row=0, column=4, padx=20)


    # -------------------------------------------------
    # TAB 1: REGISTER NEW PERSON
    # -------------------------------------------------

    def create_register_tab(self):

        frame = self.register_tab

        form = ttk.LabelFrame(frame, text="Person Details")
        form.pack(fill="x", padx=10, pady=10)

        ttk.Label(form, text="Name:").grid(
            row=0, column=0, padx=5, pady=5, sticky="e"
        )
        self.name_entry = ttk.Entry(form, width=25)
        self.name_entry.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(form, text="Age:").grid(
            row=0, column=2, padx=5, pady=5, sticky="e"
        )
        self.age_entry = ttk.Entry(form, width=10)
        self.age_entry.grid(row=0, column=3, padx=5, pady=5)

        ttk.Label(form, text="Gender:").grid(
            row=0, column=4, padx=5, pady=5, sticky="e"
        )
        self.gender_combo = ttk.Combobox(
            form, width=10, state="readonly",
            values=["Male", "Female", "Other"]
        )
        self.gender_combo.grid(row=0, column=5, padx=5, pady=5)

        ttk.Label(form, text="Family/Group ID:").grid(
            row=1, column=0, padx=5, pady=5, sticky="e"
        )
        self.family_entry = ttk.Entry(form, width=25)
        self.family_entry.grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(form, text="Phone:").grid(
            row=1, column=2, padx=5, pady=5, sticky="e"
        )
        self.phone_entry = ttk.Entry(form, width=15)
        self.phone_entry.grid(row=1, column=3, padx=5, pady=5)

        ttk.Label(form, text="Zone/Tent:").grid(
            row=1, column=4, padx=5, pady=5, sticky="e"
        )
        self.zone_entry = ttk.Entry(form, width=10)
        self.zone_entry.grid(row=1, column=5, padx=5, pady=5)

        needs_frame = ttk.LabelFrame(
            form, text="Special Needs (for priority assistance)"
        )
        needs_frame.grid(
            row=2, column=0, columnspan=6, padx=5, pady=10, sticky="w"
        )

        self.special_needs_vars = {}

        for i, need in enumerate(SPECIAL_NEEDS_OPTIONS):

            var = tk.BooleanVar(value=False)

            ttk.Checkbutton(
                needs_frame, text=need, variable=var
            ).grid(row=0, column=i, padx=10, pady=5)

            self.special_needs_vars[need] = var

        action_frame = ttk.Frame(frame)
        action_frame.pack(fill="x", padx=10, pady=5)

        self.register_button = ttk.Button(
            action_frame,
            text="Register Next Card",
            command=self.start_registration
        )
        self.register_button.pack(side="left", padx=5)

        ttk.Button(
            action_frame, text="Clear", command=self.clear_register_fields
        ).pack(side="left", padx=5)

        self.register_status_label = tk.Label(
            action_frame,
            text="Fill fields, then click 'Register Next Card'",
            fg="blue", font=("Arial", 10, "bold")
        )
        self.register_status_label.pack(side="left", padx=15)


    # -------------------------------------------------
    # TAB 2: CHECK-IN / CHECK-OUT
    # -------------------------------------------------

    def create_checkinout_tab(self):

        frame = self.checkinout_tab

        capacity_frame = ttk.LabelFrame(frame, text="Camp Capacity")
        capacity_frame.pack(fill="x", padx=10, pady=10)

        self.capacity_enabled = tk.BooleanVar(value=True)

        ttk.Checkbutton(
            capacity_frame,
            text="Enable capacity alert",
            variable=self.capacity_enabled
        ).grid(row=0, column=0, padx=10, pady=10)

        ttk.Label(capacity_frame, text="Max Capacity:").grid(
            row=0, column=1, padx=5, pady=10
        )

        self.capacity_entry = ttk.Entry(capacity_frame, width=8)
        self.capacity_entry.insert(0, str(DEFAULT_CAPACITY))
        self.capacity_entry.grid(row=0, column=2, padx=5, pady=10)

        instructions = tk.Label(
            frame,
            text="Scan a registered card to check the person IN or OUT "
                 "automatically.\nA vulnerable / special-needs person "
                 "triggers a priority alert on the kiosk.",
            font=("Arial", 11),
            justify="left"
        )
        instructions.pack(padx=10, pady=10, anchor="w")

        self.last_action_label = tk.Label(
            frame,
            text="Waiting for a card scan...",
            fg="blue",
            font=("Arial", 13, "bold")
        )
        self.last_action_label.pack(padx=10, pady=10)

        recent_frame = ttk.LabelFrame(frame, text="Recent Check-In/Out Activity")
        recent_frame.pack(fill="both", expand=True, padx=10, pady=10)

        columns = ("time", "uid", "name", "action")

        self.recent_table = ttk.Treeview(
            recent_frame, columns=columns, show="headings", height=10
        )

        for col, label, width in [
            ("time", "Time", 150),
            ("uid", "RFID UID", 120),
            ("name", "Name", 200),
            ("action", "Action", 100)
        ]:
            self.recent_table.heading(col, text=label)
            self.recent_table.column(col, width=width)

        self.recent_table.pack(fill="both", expand=True, padx=5, pady=5)

        self.refresh_recent_activity()


    # -------------------------------------------------
    # TAB 3: DASHBOARD & SEARCH
    # -------------------------------------------------

    def create_dashboard_tab(self):

        frame = self.dashboard_tab

        summary_frame = ttk.LabelFrame(frame, text="Camp Summary")
        summary_frame.pack(fill="x", padx=10, pady=10)

        self.summary_labels = {}

        summary_items = [
            ("total", "Total Registered"),
            ("in_camp", "Currently In Camp"),
            ("checked_out", "Checked Out"),
            ("vulnerable", "Vulnerable In Camp"),
            ("capacity", "Capacity")
        ]

        for i, (key, label) in enumerate(summary_items):

            box = ttk.Frame(summary_frame)
            box.grid(row=0, column=i, padx=15, pady=10)

            tk.Label(box, text=label, font=("Arial", 9)).pack()

            value_label = tk.Label(
                box, text="0", font=("Arial", 16, "bold")
            )
            value_label.pack()

            self.summary_labels[key] = value_label

        search_frame = ttk.LabelFrame(frame, text="Search Registry")
        search_frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(search_frame, text="Search (name / UID / family ID):").pack(
            side="left", padx=5, pady=8
        )

        self.search_entry = ttk.Entry(search_frame, width=30)
        self.search_entry.pack(side="left", padx=5)

        ttk.Button(
            search_frame, text="Search", command=self.refresh_dashboard
        ).pack(side="left", padx=5)

        ttk.Button(
            search_frame, text="Clear", command=self.clear_search
        ).pack(side="left", padx=5)

        ttk.Button(
            search_frame, text="Refresh", command=self.refresh_dashboard
        ).pack(side="left", padx=15)

        ttk.Button(
            search_frame, text="Export Present List (CSV)",
            command=self.export_present_list
        ).pack(side="right", padx=5)

        ttk.Button(
            search_frame, text="Export Full Registry (CSV)",
            command=self.export_full_registry
        ).pack(side="right", padx=5)

        table_frame = ttk.LabelFrame(frame, text="Registered People")
        table_frame.pack(fill="both", expand=True, padx=10, pady=10)

        columns = (
            "uid", "name", "age", "gender", "family_id",
            "phone", "zone", "special_needs", "status"
        )

        self.people_table = ttk.Treeview(
            table_frame, columns=columns, show="headings"
        )

        headers = [
            ("uid", "RFID UID", 110),
            ("name", "Name", 140),
            ("age", "Age", 50),
            ("gender", "Gender", 70),
            ("family_id", "Family ID", 90),
            ("phone", "Phone", 100),
            ("zone", "Zone", 70),
            ("special_needs", "Special Needs", 150),
            ("status", "Status", 70)
        ]

        for col, label, width in headers:
            self.people_table.heading(col, text=label)
            self.people_table.column(col, width=width)

        scrollbar = ttk.Scrollbar(
            table_frame, orient="vertical", command=self.people_table.yview
        )
        self.people_table.configure(yscrollcommand=scrollbar.set)

        self.people_table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")


    # -------------------------------------------------
    # LOG FRAME
    # -------------------------------------------------

    def create_log_frame(self):

        log_frame = ttk.LabelFrame(self.root, text="System Log")
        log_frame.pack(fill="x", padx=15, pady=10)

        self.log_text = tk.Text(log_frame, height=6)
        self.log_text.pack(fill="x", padx=5, pady=5)


    # =================================================
    # TAB / MODE HANDLING
    # =================================================

    def on_tab_changed(self, event):

        selected = self.notebook.tab(self.notebook.select(), "text")

        self.awaiting_registration = False

        if selected == "Register New Person":
            self.mode = "register"

        elif selected == "Check-In / Check-Out":
            self.mode = "checkinout"

        else:
            self.mode = "dashboard"
            self.refresh_dashboard()

        self.log("Switched to mode: " + self.mode.upper())


    # =================================================
    # COM PORT / SERIAL CONNECTION
    # =================================================

    def refresh_ports(self):

        ports = serial.tools.list_ports.comports()
        port_names = [port.device for port in ports]

        self.port_combo["values"] = port_names

        if port_names:
            self.port_combo.current(0)

    def connect_arduino(self):

        if self.serial_connection:
            self.disconnect_arduino()
            return

        port = self.port_combo.get()

        if not port:
            messagebox.showerror("Error", "Select Arduino COM Port")
            return

        try:

            self.serial_connection = serial.Serial(
                port, BAUD_RATE, timeout=1
            )

            self.running = True

            self.serial_thread = threading.Thread(
                target=self.serial_reader, daemon=True
            )
            self.serial_thread.start()

            self.connection_label.config(text="Connected", fg="green")
            self.connect_button.config(text="Disconnect")

            self.log("Arduino connected on " + port)

        except Exception as error:
            messagebox.showerror("Connection Error", str(error))

    def disconnect_arduino(self):

        self.running = False

        if self.serial_connection:
            try:
                self.serial_connection.close()
            except Exception:
                pass

        self.serial_connection = None

        self.connection_label.config(text="Disconnected", fg="red")
        self.connect_button.config(text="Connect")

        self.log("Arduino disconnected")

    def serial_reader(self):

        while self.running:

            try:

                if self.serial_connection.in_waiting:

                    message = (
                        self.serial_connection.readline()
                        .decode("utf-8", errors="ignore")
                        .strip()
                    )

                    if message:
                        self.data_queue.put(message)

            except Exception as error:
                self.data_queue.put("SERIAL_ERROR:" + str(error))
                break

    def process_serial_queue(self):

        try:
            while True:
                message = self.data_queue.get_nowait()
                self.process_arduino_message(message)

        except queue.Empty:
            pass

        self.root.after(100, self.process_serial_queue)

    def process_arduino_message(self, message):

        self.log("Arduino -> " + message)

        if message == "READY":
            self.log("RFID kiosk ready")

        elif message.startswith("CARD:"):
            uid = message[5:].strip().upper()
            self.handle_card(uid)

        elif message.startswith("SERIAL_ERROR:"):
            messagebox.showerror("Serial Error", message)

    def send_to_arduino(self, message):

        if self.serial_connection:
            try:
                self.serial_connection.write(
                    (message + "\n").encode("utf-8")
                )
                self.log("Python -> " + message)
            except Exception as error:
                self.log("Send Error: " + str(error))


    # =================================================
    # CARD DISPATCH
    # =================================================

    def handle_card(self, uid):

        if self.mode == "register":
            self.handle_register_scan(uid)

        elif self.mode == "checkinout":
            self.handle_checkinout_scan(uid)

        else:
            self.log(
                "Card scanned on Dashboard tab - ignored. "
                "Switch to Register or Check-In/Out to act on it."
            )


    # -------------------------------------------------
    # REGISTRATION FLOW
    # -------------------------------------------------

    def start_registration(self):

        if not self.serial_connection:
            messagebox.showerror(
                "Arduino Not Connected", "Connect Arduino first."
            )
            return

        name = self.name_entry.get().strip()

        if not name:
            messagebox.showwarning("Missing Data", "Enter the person's name.")
            return

        self.awaiting_registration = True

        self.register_status_label.config(
            text="SCAN RFID CARD NOW", fg="green"
        )

        self.log("Registration armed for '" + name + "'. Scan the card.")

    def get_selected_special_needs(self):

        selected = [
            need for need, var in self.special_needs_vars.items()
            if var.get()
        ]

        return ",".join(selected) if selected else "None"

    def handle_register_scan(self, uid):

        if not self.awaiting_registration:
            self.log(
                "Register tab: fill the form and click "
                "'Register Next Card' before scanning."
            )
            return

        existing = self.find_person(uid)

        if existing:

            self.send_to_arduino("EXISTS|" + existing["name"])

            self.log(
                f"DUPLICATE CARD ({uid}) already registered to "
                f"{existing['name']}"
            )

            messagebox.showwarning(
                "Already Registered",
                "This RFID card is already registered to:\n"
                + existing["name"]
            )

            self.awaiting_registration = False

            self.register_status_label.config(
                text="Fill fields, then click 'Register Next Card'",
                fg="blue"
            )

            return

        name = self.clean_text(self.name_entry.get())
        age = self.clean_text(self.age_entry.get())
        gender = self.clean_text(self.gender_combo.get())
        family_id = self.clean_text(self.family_entry.get())
        phone = self.clean_text(self.phone_entry.get())
        zone = self.clean_text(self.zone_entry.get())
        special_needs = self.get_selected_special_needs()

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        person = {
            "uid": uid,
            "name": name,
            "age": age,
            "gender": gender,
            "family_id": family_id,
            "phone": phone,
            "zone": zone,
            "special_needs": special_needs,
            "status": "IN",
            "registered_date": now,
            "last_checkin": now,
            "last_checkout": ""
        }

        self.upsert_person(person)
        self.append_checkin_log(uid, name, "REGISTER-CHECKIN")

        is_priority = special_needs != "None"

        if is_priority:
            self.send_to_arduino("REGISTEREDPRIORITY|" + name)
            self.log(f"Registered PRIORITY person: {name} ({uid})")
        else:
            self.send_to_arduino("REGISTERED|" + name)
            self.log(f"Registered {name} ({uid})")

        messagebox.showinfo(
            "Registration Successful",
            f"Name: {name}\nRFID: {uid}\n"
            f"Special Needs: {special_needs}\n\n"
            "Person marked as currently IN camp."
        )

        self.awaiting_registration = False

        self.register_status_label.config(
            text="Fill fields, then click 'Register Next Card'",
            fg="blue"
        )

        self.clear_register_fields()
        self.refresh_dashboard()
        self.check_capacity(name)


    # -------------------------------------------------
    # CHECK-IN / CHECK-OUT FLOW
    # -------------------------------------------------

    def handle_checkinout_scan(self, uid):

        person = self.find_person(uid)

        if not person:

            self.send_to_arduino("UNKNOWN|" + uid)

            self.log(f"Unknown card scanned: {uid}")

            self.last_action_label.config(
                text=f"Unknown card ({uid}) - not registered",
                fg="red"
            )

            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        is_priority = person.get("special_needs", "None") != "None"

        if person["status"] != "IN":

            person["status"] = "IN"
            person["last_checkin"] = now

            self.upsert_person(person)
            self.append_checkin_log(uid, person["name"], "IN")

            if is_priority:
                self.send_to_arduino("CHECKINPRIORITY|" + person["name"])
            else:
                self.send_to_arduino("CHECKIN|" + person["name"])

            self.last_action_label.config(
                text=f"{person['name']} CHECKED IN"
                + (" (PRIORITY)" if is_priority else ""),
                fg="green"
            )

            self.log(f"CHECK-IN: {person['name']} ({uid})")

            self.check_capacity(person["name"])

        else:

            person["status"] = "OUT"
            person["last_checkout"] = now

            self.upsert_person(person)
            self.append_checkin_log(uid, person["name"], "OUT")

            self.send_to_arduino("CHECKOUT|" + person["name"])

            self.last_action_label.config(
                text=f"{person['name']} CHECKED OUT",
                fg="blue"
            )

            self.log(f"CHECK-OUT: {person['name']} ({uid})")

        self.refresh_dashboard()
        self.refresh_recent_activity()


    def check_capacity(self, latest_name):

        if not self.capacity_enabled.get():
            return

        try:
            max_capacity = int(self.capacity_entry.get())
        except ValueError:
            return

        current_in = sum(
            1 for p in self.load_people() if p["status"] == "IN"
        )

        if current_in > max_capacity:

            self.send_to_arduino("CAMPFULL|" + latest_name)

            self.log(
                f"CAPACITY ALERT: {current_in}/{max_capacity} in camp"
            )

            messagebox.showwarning(
                "Camp At Capacity",
                f"The camp is now over capacity: "
                f"{current_in}/{max_capacity} people checked in."
            )


    # =================================================
    # DASHBOARD / SEARCH
    # =================================================

    def refresh_dashboard(self):

        people = self.load_people()

        total = len(people)
        in_camp = [p for p in people if p["status"] == "IN"]
        checked_out = [p for p in people if p["status"] == "OUT"]
        vulnerable_in_camp = [
            p for p in in_camp
            if p.get("special_needs", "None") != "None"
        ]

        try:
            max_capacity = int(self.capacity_entry.get())
            capacity_text = f"{len(in_camp)}/{max_capacity}"
        except ValueError:
            capacity_text = f"{len(in_camp)}/-"

        self.summary_labels["total"].config(text=str(total))
        self.summary_labels["in_camp"].config(text=str(len(in_camp)))
        self.summary_labels["checked_out"].config(text=str(len(checked_out)))
        self.summary_labels["vulnerable"].config(
            text=str(len(vulnerable_in_camp))
        )
        self.summary_labels["capacity"].config(text=capacity_text)

        query = self.search_entry.get().strip().lower()

        if query:
            filtered = [
                p for p in people
                if query in p["name"].lower()
                or query in p["uid"].lower()
                or query in p.get("family_id", "").lower()
            ]
        else:
            filtered = people

        for item in self.people_table.get_children():
            self.people_table.delete(item)

        for p in filtered:

            self.people_table.insert(
                "", "end",
                values=(
                    p["uid"], p["name"], p["age"], p["gender"],
                    p["family_id"], p["phone"], p["zone"],
                    p["special_needs"], p["status"]
                )
            )

    def clear_search(self):

        self.search_entry.delete(0, tk.END)
        self.refresh_dashboard()

    def refresh_recent_activity(self):

        for item in self.recent_table.get_children():
            self.recent_table.delete(item)

        if not os.path.exists(LOG_FILE):
            return

        with open(LOG_FILE, "r", newline="", encoding="utf-8") as f:

            reader = csv.reader(f)
            rows = list(reader)[1:]

        for row in rows[-30:][::-1]:

            if len(row) >= 4:
                self.recent_table.insert(
                    "", "end",
                    values=(row[0], row[1], row[2], row[3])
                )


    # =================================================
    # EXPORT
    # =================================================

    def export_present_list(self):

        people = [p for p in self.load_people() if p["status"] == "IN"]

        if not people:
            messagebox.showinfo("Nothing to Export", "No one is currently in camp.")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile="camp_present_list.csv"
        )

        if not path:
            return

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=PEOPLE_FIELDS)
            writer.writeheader()
            for p in people:
                writer.writerow(p)

        self.log("Exported present list to: " + path)
        messagebox.showinfo("Export Complete", "Present list exported successfully.")

    def export_full_registry(self):

        people = self.load_people()

        if not people:
            messagebox.showinfo("Nothing to Export", "No one is registered yet.")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile="camp_full_registry.csv"
        )

        if not path:
            return

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=PEOPLE_FIELDS)
            writer.writeheader()
            for p in people:
                writer.writerow(p)

        self.log("Exported full registry to: " + path)
        messagebox.showinfo("Export Complete", "Full registry exported successfully.")


    # =================================================
    # UTILITIES
    # =================================================

    def clean_text(self, text):

        text = text.strip()
        text = text.replace("|", " ").replace(",", " ")
        return text

    def clear_register_fields(self):

        self.name_entry.delete(0, tk.END)
        self.age_entry.delete(0, tk.END)
        self.gender_combo.set("")
        self.family_entry.delete(0, tk.END)
        self.phone_entry.delete(0, tk.END)
        self.zone_entry.delete(0, tk.END)

        for var in self.special_needs_vars.values():
            var.set(False)

    def log(self, message):

        current_time = datetime.now().strftime("%H:%M:%S")

        self.log_text.insert(tk.END, f"[{current_time}] {message}\n")
        self.log_text.see(tk.END)

    def close_application(self):

        self.running = False

        if self.serial_connection:
            try:
                self.serial_connection.close()
            except Exception:
                pass

        self.root.destroy()


# =====================================================
# PROGRAM START
# =====================================================

if __name__ == "__main__":

    root = tk.Tk()
    app = CampRegistrationApp(root)
    root.mainloop()
