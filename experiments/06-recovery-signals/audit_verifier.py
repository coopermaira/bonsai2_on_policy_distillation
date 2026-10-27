from study import BASE, WORK, JOB, docker, save, start_box, verify_session

name=f'verifier-audit-{JOB}'
start_box(name,'cmaira/bonsai-study-session:20261003')
try:
    task=BASE/'terminal-bench-tasks/tasks/session-window-debug'
    docker('cp',str(task/'environment/app')+'/.',name+':/app/app/')
    docker('exec',name,'bash','-c','find /app -name __pycache__ -type d -exec rm -rf {} +')
    save(WORK/'session-fresh-original-verification.json',verify_session(name))
    docker('cp',task/'solution',name+':/solution')
    save(WORK/'fresh-reference-setup.json',docker('exec',name,'bash','/solution/solve.sh'))
    save(WORK/'session-fresh-reference-verification.json',verify_session(name))
    qwen=next((BASE/'harbor_jobs/comparison-20260929-065104-qwen-a-session-window-debug').glob('*/artifacts/app/app'))
    docker('cp',str(qwen)+'/.',name+':/app/app/')
    docker('exec',name,'bash','-c','find /app -name __pycache__ -type d -exec rm -rf {} +')
    save(WORK/'session-qwen-artifact-verification.json',verify_session(name))
finally:
    docker('rm','-f',name,check=False)
