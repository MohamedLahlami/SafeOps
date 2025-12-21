"""
SafeOps Dashboard - Lightweight Flask server

Serves the dashboard UI and proxies API calls to the anomaly-detector service.
"""

import os
import json
from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_cors import CORS
import requests

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# Configuration
ANOMALY_DETECTOR_URL = os.getenv('ANOMALY_DETECTOR_URL', 'http://localhost:5002')
DASHBOARD_PORT = int(os.getenv('DASHBOARD_PORT', '8080'))

# In-memory storage for demo (replace with DB in production)
analysis_history = []


def load_analysis_history():
    """Load analysis history from data directory."""
    global analysis_history
    data_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
    
    if os.path.exists(data_dir):
        for f in os.listdir(data_dir):
            if f.endswith('_analysis.json'):
                try:
                    with open(os.path.join(data_dir, f)) as fp:
                        data = json.load(fp)
                        build_id = f.replace('_analysis.json', '')
                        analysis_history.append({
                            'build_id': build_id,
                            'timestamp': datetime.now().isoformat(),
                            **data
                        })
                except Exception as e:
                    print(f"Error loading {f}: {e}")


# Routes
@app.route('/')
def index():
    """Serve the main dashboard page."""
    return render_template('index.html')


@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static files."""
    return send_from_directory('static', filename)


# API Proxy Routes
@app.route('/api/health')
def health():
    """Health check."""
    try:
        resp = requests.get(f'{ANOMALY_DETECTOR_URL}/health', timeout=5)
        if resp.ok:
            return jsonify({'status': 'healthy', 'model_loaded': True})
    except:
        pass
    
    return jsonify({'status': 'healthy', 'model_loaded': False})


@app.route('/api/stats')
def stats():
    """Get statistics."""
    total = len(analysis_history)
    anomalies = sum(1 for a in analysis_history if a.get('result', {}).get('is_anomaly'))
    normal = total - anomalies
    
    return jsonify({
        'total_analyzed': total,
        'anomalies_detected': anomalies,
        'normal_builds': normal,
        'anomaly_rate': round(anomalies / max(total, 1) * 100, 1)
    })


@app.route('/api/results')
def results():
    """Get analysis results."""
    limit = request.args.get('limit', 50, type=int)
    anomalies_only = request.args.get('anomalies_only', 'false').lower() == 'true'
    
    # Format local history for frontend
    formatted = []
    for r in analysis_history:
        result_data = r.get('result', {})
        formatted.append({
            'workflow_id': r.get('build_id') or r.get('workflow_id'),
            'repo': r.get('repo') or f"{r.get('owner', '')}/{r.get('repo', '')}".strip('/'),
            'timestamp': r.get('timestamp'),
            'is_anomaly': result_data.get('is_anomaly', False),
            'anomaly_score': result_data.get('anomaly_score'),
            'confidence': result_data.get('confidence', 0.5),
            'reasons': result_data.get('anomaly_reasons', []),
            'features': r.get('features', {})
        })
    
    if anomalies_only:
        formatted = [r for r in formatted if r['is_anomaly']]
    
    # Most recent first, limited
    formatted = list(reversed(formatted[-limit:]))
    
    return jsonify({
        'count': len(formatted),
        'results': formatted
    })


@app.route('/api/results/<build_id>')
def result_detail(build_id):
    """Get details for a specific build."""
    # Check local history
    for r in analysis_history:
        if r.get('build_id') == build_id:
            return jsonify(r)
    
    # Try anomaly detector
    try:
        resp = requests.get(f'{ANOMALY_DETECTOR_URL}/results/{build_id}', timeout=5)
        if resp.ok:
            return jsonify(resp.json())
    except:
        pass
    
    return jsonify({'error': 'Build not found'}), 404


@app.route('/api/model/info')
def model_info():
    """Get model information."""
    try:
        resp = requests.get(f'{ANOMALY_DETECTOR_URL}/model/info', timeout=5)
        if resp.ok:
            return jsonify(resp.json())
    except:
        pass
    
    return jsonify({'error': 'Could not fetch model info'}), 503


@app.route('/api/analyze', methods=['POST'])
def analyze():
    """Analyze a GitHub workflow."""
    data = request.get_json()
    
    owner = data.get('owner')
    repo = data.get('repo')
    run_id = data.get('run_id') or data.get('workflow_id')
    
    if not all([owner, repo, run_id]):
        return jsonify({'error': 'Missing owner, repo, or workflow_id'}), 400
    
    # Run the analysis script
    import subprocess
    import sys
    
    script_path = os.path.join(os.path.dirname(__file__), '..', '..', 'scripts', 'test_real_workflow.py')
    
    try:
        result = subprocess.run(
            [sys.executable, script_path, owner, repo, str(run_id)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=os.path.join(os.path.dirname(__file__), '..', '..')
        )
        
        # Load the result
        result_file = os.path.join(os.path.dirname(__file__), '..', '..', 'data', f'{run_id}_analysis.json')
        if os.path.exists(result_file):
            with open(result_file) as f:
                analysis = json.load(f)
            
            # Add to history
            analysis_history.append({
                'build_id': str(run_id),
                'owner': owner,
                'repo': repo,
                'timestamp': datetime.now().isoformat(),
                **analysis
            })
            
            return jsonify({
                'status': 'success',
                'workflow_id': str(run_id),
                'repo': f'{owner}/{repo}',
                'is_anomaly': analysis.get('result', {}).get('is_anomaly', False),
                'anomaly_score': analysis.get('result', {}).get('anomaly_score'),
                'features': analysis.get('features', {}),
                'reasons': analysis.get('result', {}).get('anomaly_reasons', [])
            })
        else:
            return jsonify({
                'status': 'error',
                'error': 'Analysis completed but no result file found',
                'stdout': result.stdout,
                'stderr': result.stderr
            }), 500
            
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Analysis timed out'}), 504
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/workflows')
def list_workflows():
    """List available workflows from GitHub."""
    # This would require GitHub token - simplified for now
    return jsonify({
        'message': 'Use the analyze endpoint with owner/repo/run_id'
    })


if __name__ == '__main__':
    load_analysis_history()
    print(f"Starting SafeOps Dashboard on port {DASHBOARD_PORT}")
    print(f"Anomaly Detector URL: {ANOMALY_DETECTOR_URL}")
    print(f"Loaded {len(analysis_history)} historical analyses")
    app.run(host='0.0.0.0', port=DASHBOARD_PORT, debug=True)
