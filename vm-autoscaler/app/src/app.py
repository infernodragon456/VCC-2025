#!/usr/bin/env python3
import os
import time
import threading
import psutil
from flask import Flask, render_template, jsonify, request

app = Flask(__name__, 
            template_folder='../templates',
            static_folder='../static')

# Global variables for stress testing
cpu_stress_threads = []
mem_chunks = []

def cpu_stress_task():
    """Task that consumes CPU"""
    end_time = time.time() + 120  # Run for 2 minutes
    while time.time() < end_time:
        # CPU intensive calculation
        _ = [i**2 for i in range(10000)]

@app.route('/')
def index():
    """Main application page"""
    hostname = os.environ.get('HOSTNAME', 'local')
    deployment = os.environ.get('DEPLOYMENT', 'unknown')
    return render_template('index.html', hostname=hostname, deployment=deployment)

@app.route('/metrics')
def metrics():
    """Return current resource metrics"""
    cpu_percent = psutil.cpu_percent()
    mem_percent = psutil.virtual_memory().percent
    return jsonify({
        'cpu_percent': cpu_percent,
        'mem_percent': mem_percent,
        'hostname': os.environ.get('HOSTNAME', 'local'),
        'deployment': os.environ.get('DEPLOYMENT', 'unknown')
    })

@app.route('/stress/cpu')
def stress_cpu():
    """Endpoint to stress CPU"""
    global cpu_stress_threads
    
    # Clean up finished threads
    cpu_stress_threads = [t for t in cpu_stress_threads if t.is_alive()]
    
    # Number of threads to create (default: 2)
    num_threads = int(request.args.get('threads', 2))
    
    # Create new stress threads
    for _ in range(num_threads):
        thread = threading.Thread(target=cpu_stress_task)
        thread.daemon = True
        thread.start()
        cpu_stress_threads.append(thread)
    
    return jsonify({
        'status': 'started',
        'active_threads': len(cpu_stress_threads),
        'message': f'Started {num_threads} CPU stress threads'
    })

@app.route('/stress/memory')
def stress_memory():
    """Endpoint to stress memory"""
    global mem_chunks
    
    # Size in MB (default: 100MB)
    size_mb = int(request.args.get('size', 100))
    
    # Allocate memory (each chunk is 1MB)
    for _ in range(size_mb):
        mem_chunks.append(' ' * 1024 * 1024)  # Allocate 1MB
    
    return jsonify({
        'status': 'allocated',
        'total_allocated_mb': len(mem_chunks),
        'message': f'Allocated {size_mb}MB of memory'
    })

@app.route('/stress/clear')
def clear_stress():
    """Clear all stress tests"""
    global cpu_stress_threads, mem_chunks
    
    # We can't really stop the threads, but we can clear the list
    # They will finish on their own after their time period
    active_threads = len(cpu_stress_threads)
    cpu_stress_threads = []
    
    # Clear memory
    mem_allocated = len(mem_chunks)
    mem_chunks = []
    
    return jsonify({
        'status': 'cleared',
        'cleared_threads': active_threads,
        'cleared_memory_mb': mem_allocated,
        'message': 'Cleared all stress tests'
    })

if __name__ == '__main__':
    # Run on all interfaces, port 8080
    app.run(host='0.0.0.0', port=8080) 