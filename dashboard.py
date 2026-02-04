import streamlit as st
import subprocess
import re
import plotly.graph_objects as go
import os
import sys
import time

# -----------------------------------------------------------------------------
# Page Configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="xv6 Fork Analysis",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------------------------------
# Styling & Helpers
# -----------------------------------------------------------------------------
st.markdown("""
<style>
    .main .block-container {
        padding-top: 2rem;
    }
    h1 {
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-weight: 700;
        color: #2c3e50;
    }
    .stButton button {
        width: 100%;
        border-radius: 5px;
        height: 3em;
        font-weight: 600;
    }
    div[data-testid="stMetric"] {
        background-color: #f8f9fa;
        padding: 15px;
        border-radius: 8px;
        border-left: 5px solid #3498db;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Simulation Logic
# -----------------------------------------------------------------------------
def run_simulation(forks):
    """
    Runs the xv6 simulation via QEMU and captures the output.
    Returns: Dictionary containing parsed results or None on failure.
    """
    cmd_sequence = [
        f"bench {forks} 0 0\n", # STD, NoWrite
        f"bench {forks} 1 0\n", # COW, NoWrite
        f"bench {forks} 0 1\n", # STD, Write
        f"bench {forks} 1 1\n"  # COW, Write
    ]
    
    status_text = st.empty()
    progress_bar = st.progress(0)
    
    try:
        status_text.text("Starting QEMU environment...")
        process = subprocess.Popen(
            ["make", "qemu"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, 
            text=True,
            cwd=os.getcwd(),
            bufsize=0 
        )
        
        total_output = ""
        current_chunk = ""
        booted = False
        cmds_sent = 0
        
        # We need a robust loop to read output and send commands
        start_time = time.time()
        
        while True:
            # Check for timeout just in case
            if time.time() - start_time > 60:
                process.kill()
                st.error("Simulation timed out.")
                return None

            # Non-blocking read (character by character for pattern matching)
            char = process.stdout.read(1)
            
            if not char and process.poll() is not None:
                break
                
            if char:
                current_chunk += char
                total_output += char
                
                # Check for prompt
                if "$ " in current_chunk:
                    if not booted:
                        booted = True
                        status_text.text("System booted. Running benchmark 1/4...")
                        process.stdin.write(cmd_sequence[0])
                        process.stdin.flush()
                        cmds_sent += 1
                        current_chunk = ""
                        progress_bar.progress(25)
                    elif cmds_sent < len(cmd_sequence):
                        status_text.text(f"Running benchmark {cmds_sent + 1}/4...")
                        process.stdin.write(cmd_sequence[cmds_sent])
                        process.stdin.flush()
                        cmds_sent += 1
                        current_chunk = ""
                        progress_bar.progress(25 + (cmds_sent * 18)) # scale nicely
                    else:
                        status_text.text("Benchmarks complete. Exiting...")
                        process.stdin.write("\x01x") # Ctrl-A + x to exit QEMU
                        process.stdin.flush()
                        break
        
        process.wait()
        progress_bar.progress(100)
        status_text.text("Simulation finished.")
        return parse_results(total_output)
        
    except Exception as e:
        st.error(f"Simulation failed: {e}")
        return None

def parse_results(output):
    """
    Parses the QEMU output for benchmark data.
    Pattern: DATA:Type,WriteMode,Ticks,PagesConsumed
    """
    # Debug: show raw output if needed (commented out)
    # with st.expander("Raw Output"):
    #     st.code(output)

    pattern = r"DATA:(STD|COW),(WRITE|NOWRITE),(\d+),(\d+)"
    matches = re.findall(pattern, output)
    
    if not matches:
        st.error("No benchmark data found in output. Please check if 'bench' command exists in xv6.")
        return None
        
    results = {
        "NOWRITE": {"STD": {}, "COW": {}},
        "WRITE":   {"STD": {}, "COW": {}}
    }

    for type_, write_mode, ticks, pages in matches:
        results[write_mode][type_] = {"ticks": int(ticks), "pages": int(pages)}
        
    return results

# -----------------------------------------------------------------------------
# Visualization Helpers
# -----------------------------------------------------------------------------
def create_comparison_chart(data, metric, title, y_label, color_seq):
    """
    Creates a grouped bar chart for comparison.
    """
    std_val = data["STD"].get(metric, 0)
    cow_val = data["COW"].get(metric, 0)
    
    fig = go.Figure(data=[
        go.Bar(name='Standard Fork', x=['Algorithm'], y=[std_val], marker_color=color_seq[0], text=std_val, textposition='auto'),
        go.Bar(name='COW Fork', x=['Algorithm'], y=[cow_val], marker_color=color_seq[1], text=cow_val, textposition='auto')
    ])
    
    fig.update_layout(
        title=title,
        yaxis_title=y_label,
        barmode='group',
        height=350,
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    return fig

# -----------------------------------------------------------------------------
# Main UI
# -----------------------------------------------------------------------------

# Sidebar Setup
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/c/c3/Python-logo-notext.svg/1200px-Python-logo-notext.svg.png", width=50)
    st.header("Settings")
    
    forks_input = st.number_input(
        "Number of Forks", 
        min_value=10, 
        max_value=2000, 
        value=50, 
        step=10,
        help="How many times the child process will be forked."
    )
    
    st.info("""
    **Instructions:**
    1. Enter number of forks.
    2. Click 'Run Simulation'.
    3. Wait for QEMU to execute benchmarks.
    """)
    
    run_clicked = st.button("Run Simulation", type="primary")

# Main Content
st.title("xv6 Fork Performance Analysis")
st.markdown("Quantifying the benefits of **Copy-On-Write** optimization in process creation.")

if run_clicked:
    with st.spinner("Initializing simulation environment..."):
        results = run_simulation(int(forks_input))
    
    if results:
        # Create Tabs for Scenarios
        tab1, tab2 = st.tabs(["📄 Read-Only Workload", "📝 Write-Heavy Workload"])
        
        # --- TAB 1: Read Note ---
        with tab1:
            st.caption("Child process exits immediately without modifying memory.")
            
            # Metrics Row
            std_time = results["NOWRITE"]["STD"].get("ticks", 0)
            cow_time = results["NOWRITE"]["COW"].get("ticks", 0)
            std_mem = results["NOWRITE"]["STD"].get("pages", 0)
            cow_mem = results["NOWRITE"]["COW"].get("pages", 0)
            
            curr_col1, curr_col2, curr_col3 = st.columns(3)
            with curr_col1:
                st.metric(label="Time Improvement", value=f"{cow_time} ticks", delta=f"{std_time - cow_time} ticks faster")
            with curr_col2:
                st.metric(label="Memory Savings", value=f"{cow_mem} pages", delta=f"{std_mem - cow_mem} pages saved", delta_color="normal")
            
            # Charts Row
            c1, c2 = st.columns(2)
            with c1:
                fig_time = create_comparison_chart(results["NOWRITE"], "ticks", "Execution Time (Lower is Better)", "Ticks", ['#95a5a6', '#2ecc71'])
                st.plotly_chart(fig_time, use_container_width=True)
            with c2:
                fig_mem = create_comparison_chart(results["NOWRITE"], "pages", "Memory Consumption (Lower is Better)", "Pages", ['#e74c3c', '#f1c40f'])
                st.plotly_chart(fig_mem, use_container_width=True)

        # --- TAB 2: Write Note ---
        with tab2:
            st.caption("Child process modifies memory immediately after fork.")
            
            # Metrics Row
            std_time_w = results["WRITE"]["STD"].get("ticks", 0)
            cow_time_w = results["WRITE"]["COW"].get("ticks", 0)
            std_mem_w = results["WRITE"]["STD"].get("pages", 0)
            cow_mem_w = results["WRITE"]["COW"].get("pages", 0)
            
            w_col1, w_col2, w_col3 = st.columns(3)
            with w_col1:
                st.metric(label="Time Difference", value=f"{cow_time_w} ticks", delta=f"{std_time_w - cow_time_w} ticks")
            with w_col2:
                st.metric(label="Memory Difference", value=f"{cow_mem_w} pages", delta=f"{std_mem_w - cow_mem_w} pages")

            # Charts Row
            c1, c2 = st.columns(2)
            with c1:
                fig_time_w = create_comparison_chart(results["WRITE"], "ticks", "Execution Time (Write Heavy)", "Ticks", ['#95a5a6', '#27ae60'])
                st.plotly_chart(fig_time_w, use_container_width=True)
            with c2:
                fig_mem_w = create_comparison_chart(results["WRITE"], "pages", "Memory Consumption (Write Heavy)", "Pages", ['#c0392b', '#f39c12'])
                st.plotly_chart(fig_mem_w, use_container_width=True)

else:
    # Placeholder / Empty State
    st.info("👈 Set the number of forks and click 'Run Simulation' to start.")
    
    # Show dummy data or explanation
    st.subheader("What does this test?")
    st.markdown("""
    This dashboard runs a benchmark program (`bench.c`) inside the xv6 operating system running on QEMU.
    
    It compares two fork implementations:
    1.  **Standard Fork**: Copies all memory pages from parent to child eagerly.
    2.  **COW Fork**: Shares memory pages initially and only copies them when modified.
    
    **Hypothesis:**
    - **Read-Only**: COW should be significantly faster and use less memory.
    - **Write-Heavy**: COW overhead (page faults) might make it perform similarly slightly slower than Standard Fork.
    """)
