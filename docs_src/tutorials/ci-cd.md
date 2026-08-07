# CI/CD Integration

Gate agent quality in your pipelines — fail builds when agents are sloppy.

## GitHub Actions

### Basic Workflow

```yaml
# .github/workflows/agent-quality.yml
name: Agent Quality Gate

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  agent-eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      
      - name: Install AgentDiff
        run: pip install agentdiff
      
      - name: Capture baseline
        run: agentdiff snapshot -o before.json
      
      - name: Run agent
        run: python run_agent.py  # Your agent script
        # Ensure your agent saves trajectory.json
      
      - name: Capture post state
        run: agentdiff snapshot -o after.json
      
      - name: Evaluate with AgentDiff
        run: |
          agentdiff eval \
            --trajectory trajectory.json \
            --pre before.json \
            --post after.json \
            --fail-below 0.85
```

### With JUnit Output (for PR annotations)

```yaml
- name: Evaluate with JUnit output
  run: |
    agentdiff eval \
      --trajectory trajectory.json \
      --pre before.json \
      --post after.json \
      --fail-below 0.85 \
      --junit report.xml

- name: Publish test results
  uses: actions/upload-artifact@v4
  with:
    name: agentdiff-report
    path: report.xml
```

### Fail PR on Low Cleanliness

```yaml
- name: Check cleanliness threshold
  run: |
    REPORT=$(agentdiff eval -t trajectory.json --pre before.json --post after.json --format json)
    CLEANLINESS=$(echo $REPORT | jq -r '.cleanliness_score')
    THRESHOLD=0.85
    
    if (( $(echo "$CLEANLINESS < $THRESHOLD" | bc -l) )); then
      echo "::error::Cleanliness $CLEANLINESS below threshold $THRESHOLD"
      exit 1
    fi
```

## GitLab CI

```yaml
# .gitlab-ci.yml
agent_quality:
  stage: test
  image: python:3.11
  script:
    - pip install agentdiff
    - agentdiff snapshot -o before.json
    - python run_agent.py
    - agentdiff snapshot -o after.json
    - agentdiff eval -t trajectory.json --pre before.json --post after.json --fail-below 0.85
  artifacts:
    reports:
      junit: report.xml
    when: always
```

## Jenkins Pipeline

```groovy
pipeline {
    agent any
    stages {
        stage('Agent Eval') {
            steps {
                sh 'pip install agentdiff'
                sh 'agentdiff snapshot -o before.json'
                sh 'python run_agent.py'
                sh 'agentdiff snapshot -o after.json'
                sh '''
                    agentdiff eval \
                        -t trajectory.json \
                        --pre before.json \
                        --post after.json \
                        --fail-below 0.85 \
                        --junit report.xml
                '''
            }
            post {
                always {
                    junit 'report.xml'
                }
            }
        }
    }
}
```

## Pre-commit Hook (Local)

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: agentdiff
        name: AgentDiff Quality Check
        entry: agentdiff eval -t trajectory.json --pre before.json --post after.json --fail-below 0.8
        language: system
        pass_filenames: false
        always_run: true
```

## Quality Gate Strategies

| Strategy | Threshold | Use Case |
|----------|-----------|----------|
| **Strict** | 0.95 | Production agents, security-sensitive |
| **Standard** | 0.80 | General purpose, CI gate |
| **Lenient** | 0.60 | Experimental, research, early dev |
| **Monitor Only** | 0.00 | Baseline collection, no failures |

## Badge for README

```markdown
![AgentDiff Cleanliness](https://img.shields.io/endpoint?url=https://agentdiff.dev/badge/your-repo.json)
```

## Related

- [CLI Reference](../cli.md) — All eval options
- [Python API](../api.md) — Programmatic evaluation