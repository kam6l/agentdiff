# Benchmarking Agents

Use AgentDiff to objectively compare agent implementations, models, and prompts.

## Why Benchmark with AgentDiff?

Traditional benchmarks (SWE-bench, WebArena) only measure **outcome**: pass/fail.

AgentDiff measures **quality of execution**:
- Cleanliness Score (collateral damage)
- Efficiency (steps, loops, redundant calls)
- Side Effect Profile (what broke)
- Step-level fault attribution

## Quick Benchmark

```bash
# Run multiple agents on same task
agentdiff benchmark \
  --task "Fix the add() function in calculator.py" \
  --agents "langgraph,crewai,autogen" \
  --runs 5 \
  --output benchmark.json
```

## Programmatic Benchmarking

```python
from agentdiff import AgentDiffSession, benchmark
from agentdiff.integrations import LangChainCallbackHandler, CrewAIAdapter

agents = {
    "langgraph-gpt4": lambda: create_langgraph_agent("gpt-4"),
    "langgraph-claude": lambda: create_langgraph_agent("claude-3"),
    "crewai-gpt4": lambda: create_crewai_agent("gpt-4"),
    "custom-agent": lambda: MyCustomAgent(),
}

results = benchmark(
    agents=agents,
    task="Refactor the user authentication module",
    repo_path="/repo",
    target_paths=["/repo/src/auth/"],
    runs=3,  # Statistical significance
)

# Results: DataFrame with cleanliness, efficiency, side effects per agent/run
print(results.summary())
"""
                    cleanliness  efficiency  side_effects  duration_s
agent           run                                         
langgraph-gpt4  0        0.92      0.88            1        45.2
                1        0.89      0.91            2        42.1
                2        0.94      0.85            0        48.7
langgraph-claude 0       0.96      0.93            0        52.3
                ...
"""
```

## Statistical Comparison

```python
import pandas as pd

df = results.to_dataframe()

# Mean cleanliness per agent
print(df.groupby("agent")["cleanliness"].mean())
"""
agent
langgraph-claude    0.95
langgraph-gpt4      0.92
crewai-gpt4         0.78
custom-agent        0.65
"""

# Significance test
from scipy import stats
stat, p = stats.ttest_ind(
    df[df.agent=="langgraph-claude"]["cleanliness"],
    df[df.agent=="crewai-gpt4"]["cleanliness"]
)
print(f"p-value: {p:.4f}")  # p < 0.05 = significant difference
```

## SWE-bench Integration

```bash
# Evaluate on SWE-bench trajectories
agentdiff eval --dataset swe-bench --split test --output swe_results.json

# Compare with published baselines
agentdiff compare --baseline swe_bench_paper.csv --current swe_results.json
```

## Custom Benchmark Suite

```python
from agentdiff import BenchmarkSuite

suite = BenchmarkSuite(name="my-org-agents")

suite.add_task(
    name="bugfix-auth",
    description="Fix authentication bypass in login.py",
    repo_path="/benchmarks/auth-bug",
    target_paths=["/benchmarks/auth-bug/login.py"],
    setup_script="git checkout buggy-version",
)

suite.add_task(
    name="refactor-user-service",
    description="Extract UserService from monolith",
    repo_path="/benchmarks/monolith",
    target_paths=["/benchmarks/monolith/services/user/"],
)

suite.add_agent("langgraph-gpt4", create_langgraph_gpt4)
suite.add_agent("langgraph-claude", create_langgraph_claude)
suite.add_agent("my-custom", MyCustomAgent)

results = suite.run(runs=3)
results.save("benchmark_results.json")
results.to_html("benchmark_report.html")
```

## CI Benchmarking (Nightly)

```yaml
# .github/workflows/nightly-benchmark.yml
name: Nightly Agent Benchmark

on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM daily

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      
      - name: Run benchmark suite
        run: |
          pip install agentdiff
          python run_benchmarks.py
      
      - name: Upload results
        uses: actions/upload-artifact@v4
        with:
          name: benchmark-results
          path: benchmark_results.json
      
      - name: Post to dashboard
        run: |
          curl -X POST https://agentdiff.dev/api/benchmark \
            -H "Authorization: Bearer ${{ secrets.AGENTDIFF_TOKEN }}" \
            -d @benchmark_results.json
```

## Visualizing Results

```python
# Built-in visualization
results.to_html("report.html")  # Interactive charts

# Or with matplotlib/seaborn
import seaborn as sns
import matplotlib.pyplot as plt

df = results.to_dataframe()

# Cleanliness distribution
sns.boxplot(data=df, x="agent", y="cleanliness")
plt.title("Cleanliness Score by Agent")
plt.savefig("cleanliness_boxplot.png")

# Efficiency vs Cleanliness scatter
sns.scatterplot(data=df, x="efficiency", y="cleanliness", hue="agent")
plt.savefig("efficiency_vs_cleanliness.png")
```

## Publishing Results

```bash
# Generate shareable report
agentdiff report benchmark_results.json --html --public

# Uploads to https://agentdiff.dev/b/abc123
# Shareable link with interactive filters
```

## Related

- [CI/CD Integration](ci-cd.md) — Gate quality in pipelines
- [Python API](../api.md) — Programmatic evaluation