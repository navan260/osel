import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import re
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import threading
import os
import sys

class XV6Visualizer:
    def __init__(self, root):
        self.root = root
        self.root.title("XV6 Fork vs CowFork Visualizer")
        self.root.geometry("1000x800") # Increased size for 2x2
        
        # Initialize process variable
        self.process = None

        # Bind closing event
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Style
        style = ttk.Style()
        style.theme_use('clam')

        # Input Frame
        input_frame = ttk.Frame(root, padding="20")
        input_frame.pack(fill=tk.X)

        ttk.Label(input_frame, text="Number of Forks:").pack(side=tk.LEFT, padx=5)
        self.forks_entry = ttk.Entry(input_frame, width=10)
        self.forks_entry.pack(side=tk.LEFT, padx=5)
        self.forks_entry.insert(0, "50")

        self.visualize_btn = ttk.Button(input_frame, text="Visualize", command=self.start_visualization)
        self.visualize_btn.pack(side=tk.LEFT, padx=20)

        self.status_label = ttk.Label(input_frame, text="Ready", foreground="gray")
        self.status_label.pack(side=tk.LEFT, padx=20)

        # Graph Frame
        self.graph_frame = ttk.Frame(root, padding="10")
        self.graph_frame.pack(fill=tk.BOTH, expand=True)

        # 2x2 Subplots
        self.figure, self.axes = plt.subplots(2, 2, figsize=(10, 8))
        # axes is [[ax1, ax2], [ax3, ax4]]
        # Row 0: No Write (Time, Mem)
        # Row 1: With Write (Time, Mem)
        
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.graph_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def on_close(self):
        """Handle window close event"""
        if self.process and self.process.poll() is None:
            print("Terminating QEMU process...")
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                print("Force killing QEMU...")
                self.process.kill()
        
        self.root.destroy()
        sys.exit(0)

    def start_visualization(self):
        try:
            forks = int(self.forks_entry.get())
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid integer for forks.")
            return

        self.status_label.config(text="Running simulation in QEMU... Please wait.")
        self.visualize_btn.config(state=tk.DISABLED)
        
        # Run in a separate thread
        threading.Thread(target=self.run_simulation, args=(forks,), daemon=True).start()

    def run_simulation(self, forks):
        results = {}
        try:
            self.process = subprocess.Popen(
                ["make", "qemu"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, 
                text=True,
                cwd=os.getcwd(),
                bufsize=0 
            )

            print("Simulation started...")
            
            def write_cmd(cmd):
                print(f"Sending: {cmd.strip()}")
                if self.process and self.process.poll() is None:
                    self.process.stdin.write(cmd)
                    self.process.stdin.flush()

            total_output = ""
            current_output_chunk = ""
            
            booted = False
            # 4 Commands: 
            # 1. STD NoWrite (0 0)
            # 2. COW NoWrite (1 0)
            # 3. STD Write (0 1)
            # 4. COW Write (1 1)
            commands = [
                f"bench {forks} 0 0\n",
                f"bench {forks} 1 0\n",
                f"bench {forks} 0 1\n",
                f"bench {forks} 1 1\n"
            ]
            
            commands_sent = 0

            while True:
                # Check directly if process ended unexpectedly
                if self.process.poll() is not None:
                    break
                    
                char = self.process.stdout.read(1)
                if not char:
                    break
                
                current_output_chunk += char
                total_output += char
                sys.stdout.write(char)
                
                if "$ " in current_output_chunk:
                    # Found a prompt
                    if not booted:
                        print("\n[DEBUG] Boot detected")
                        booted = True
                        current_output_chunk = ""
                        # Send first command
                        write_cmd(commands[commands_sent])
                        commands_sent += 1
                        
                    elif commands_sent < len(commands):
                        print(f"\n[DEBUG] Command {commands_sent} finished")
                        current_output_chunk = ""
                        # Send next command
                        write_cmd(commands[commands_sent])
                        commands_sent += 1
                        
                    else:
                        print("\n[DEBUG] All commands finished")
                        write_cmd("\x01x")
                        break

            # Wait for process to exit
            self.process.wait()

            # Parse Output
            print("\nParsing results from captured output...")
            # Pattern: DATA:Type,WriteMode,Ticks,PagesConsumed
            pattern = r"DATA:(STD|COW),(WRITE|NOWRITE),(\d+),(\d+)"
            matches = re.findall(pattern, total_output)
            
            print("Captured matches:", matches) 
            
            # Organize results: results[WriteMode][Type] = {ticks, pages}
            results = {
                "NOWRITE": {"STD": {}, "COW": {}},
                "WRITE":   {"STD": {}, "COW": {}}
            }

            for type_, write_mode, ticks, pages in matches:
                results[write_mode][type_] = {"ticks": int(ticks), "pages": int(pages)}

            self.root.after(0, self.update_plot, results)

        except Exception as e:
            print(f"Error: {e}")
            if self.process and self.process.poll() is None: # Only show error if we didn't deliberately kill it
                 self.root.after(0, lambda: messagebox.showerror("Execution Error", str(e)))
        finally:
            self.root.after(0, lambda: self.visualize_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.status_label.config(text="Done"))

    def update_plot(self, results):
        if not results:
            # Check if this was a user abort
            if self.process and self.process.poll() is not None:
                 print("Process ended without data (likely closed).")
                 return
            
            messagebox.showwarning("No Data", "Could not parse data from QEMU output.")
            return

        for ax_row in self.axes:
            for ax in ax_row:
                ax.clear()

        # Helper to plot
        def plot_scenario(ax_time, ax_mem, scenario_data, title_prefix):
            types = ["STD", "COW"]
            std_res = scenario_data.get("STD", {"ticks": 0, "pages": 0})
            cow_res = scenario_data.get("COW", {"ticks": 0, "pages": 0})
            
            ticks = [std_res.get("ticks",0), cow_res.get("ticks",0)]
            pages = [std_res.get("pages",0), cow_res.get("pages",0)]

            # Plot Time
            bars1 = ax_time.bar(types, ticks, color=['#3498db', '#2ecc71'])
            ax_time.set_title(f"{title_prefix} - Time (Ticks)")
            ax_time.set_ylabel("Ticks")
            ax_time.bar_label(bars1)

            # Plot Memory
            bars2 = ax_mem.bar(types, pages, color=['#e74c3c', '#f39c12'])
            ax_mem.set_title(f"{title_prefix} - Memory (Pages)")
            ax_mem.set_ylabel("Pages")
            ax_mem.bar_label(bars2)

        # Row 0: No Write
        plot_scenario(self.axes[0][0], self.axes[0][1], results["NOWRITE"], "Read-Only")
        
        # Row 1: Write
        plot_scenario(self.axes[1][0], self.axes[1][1], results["WRITE"], "Write-Heavy")

        self.figure.tight_layout()
        self.canvas.draw()

if __name__ == "__main__":
    if "DISPLAY" not in os.environ:
         print("Warning: DISPLAY environment variable not set. GUI may fail to open.")
    
    root = tk.Tk()
    app = XV6Visualizer(root)
    root.mainloop()
