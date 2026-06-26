import os
os.environ['PYTHONPATH'] = r'D:\develop\AgentProjects\goals\backend'
import uvicorn
uvicorn.run('main:app', host='0.0.0.0', port=8765)
