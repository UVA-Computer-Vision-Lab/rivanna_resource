import subprocess
import re
import itertools
import pandas as pd

def get_node_names(partition_name):
    # Get node names list
    sinfo_cmd = ["sinfo", "-p", partition_name]
    result = subprocess.run(sinfo_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    if result.returncode != 0:
        print("Error fetching nodes:", result.stderr)
        return []

    # Parse the output to extract node names
    node_names = set()
    for line in result.stdout.splitlines():
        if not line.startswith("PARTITION") and line.strip():
            parts = line.split()
            if len(parts) >= 5:
                nodelist = parts[-1]
                # Process node list (e.g., udc-an38-[1,9,13,17,25,29,33])
                expanded_nodes = expand_nodelist(nodelist)
                node_names.update(expanded_nodes)
    
    return list(node_names)

def expand_nodelist(nodelist):
    # Use regex to expand node list
    expanded_nodes = []
    pattern = re.compile(r'([a-zA-Z\-\d]+)\[(\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*)\]')
    matches = pattern.findall(nodelist)
    if matches:
        for match in matches:
            prefix, ids = match
            for part in ids.split(','):
                if '-' in part:
                    start, end = map(int, part.split('-'))
                    expanded_nodes.extend([f"{prefix}{i}" for i in range(start, end + 1)])
                else:
                    expanded_nodes.append(f"{prefix}{part}")
    else:
        expanded_nodes.append(nodelist)
    
    return expanded_nodes

def get_node_resources(node_name):
    # Get node resource information
    scontrol_cmd = ["scontrol", "show", "node", node_name]
    result = subprocess.run(scontrol_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    if result.returncode != 0:
        print(f"Error fetching node {node_name} info:", result.stderr)
        return None

    # Extract current available CPU, memory, and GPU information using regex
    cpu_alloc_match = re.search(r'CPUAlloc=(\d+)', result.stdout)
    cpu_total_match = re.search(r'CPUTot=(\d+)', result.stdout)
    mem_alloc_match = re.search(r'AllocMem=(\d+)', result.stdout)
    mem_total_match = re.search(r'RealMemory=(\d+)', result.stdout)
    gpu_alloc_match = re.search(r'AllocTRES=.*gres/gpu=(\d+)', result.stdout)
    gpu_total_match = re.findall(r'Gres=gpu:(\w+(?:-\d+)?):\d+', result.stdout)
    available_features_match = re.search(r'AvailableFeatures=([\w,]+)', result.stdout)

    cpus_total = int(cpu_total_match.group(1)) if cpu_total_match else None
    cpus_alloc = int(cpu_alloc_match.group(1)) if cpu_alloc_match else None
    cpus_available = cpus_total - cpus_alloc if cpus_total is not None and cpus_alloc is not None else None

    memory_total = int(mem_total_match.group(1)) if mem_total_match else None
    memory_alloc = int(mem_alloc_match.group(1)) if mem_alloc_match else None
    memory_available = memory_total - memory_alloc if memory_total is not None and memory_alloc is not None else None
    memory_available_gb = (memory_available // 102.4) / 10 if memory_available is not None else None

    gpus_available = 0
    gpu_type = []
    if available_features_match:
        gpu_type = available_features_match.group(1).split(',')
    if gpu_total_match:
        for gpu in gpu_total_match:
            gpu_model = gpu
            gpus_alloc = int(gpu_alloc_match.group(1)) if gpu_alloc_match else 0
            gpus_available += 8 - gpus_alloc if gpus_alloc is not None else 8
    gpu_type = [tp for tp in gpu_type if "gb" in tp] if len(gpu_type) > 1 else gpu_type
    gpu_type_str = ", ".join(gpu_type) if gpu_type else None

    return {
        'Node': node_name,
        'Available CPUs': cpus_available,
        'Available Memory (GB)': memory_available_gb,
        'Available GPUs': gpus_available,
        'GPU Type': gpu_type_str
    }

def main():
    partitions = ["gpu-a6000", "gpu-a100-80", "gpu-a100-40", "gpu-a40", "gpu-v100", "interactive"]
    all_resources = []
    
    for partition_name in partitions:
        print(f"Checking partition: {partition_name}")
        node_names = get_node_names(partition_name)

        if not node_names:
            print("No nodes found for partition:", partition_name)
            continue

        for node in node_names:
            resources = get_node_resources(node)
            if resources:
                all_resources.append(resources)
    
    if all_resources:
        df = pd.DataFrame(all_resources)
        df_filtered = df[(df['Available GPUs'] > 0) & (df['Available CPUs'] > 0) & (df['Available Memory (GB)'] >= 6)]
        print(df_filtered)

if __name__ == "__main__":
    main()