# AgentDiff API migration demos

These fixtures tell both halves of the product story. They contain no API key
and make no network request.

Run the read-only plan:

```bash
agentdiff api simulate --root demos/openai-success --provider openai --change chat_to_responses
```

Run the supported migration (Docker required for clean-room proof):

```bash
agentdiff api migrate --root demos/openai-success --provider openai --change chat_to_responses
```

Run the unsafe-worker rejection:

```bash
agentdiff api migrate --root demos/openai-failure --provider openai \
  --change chat_to_responses --generator command \
  --generator-argv python3 unsafe_generator.py
```

The source fixtures remain unchanged. Generated evidence and certificates live
under each fixture's ignored `.agentdiff/` directory.

Run a read-only repository campaign with supported, review-required, and
unaffected outcomes:

```bash
agentdiff fleet simulate --config demos/fleet/fleet.yaml
```

`fleet migrate` uses the same clean-room proof requirements as a single
repository and therefore requires Docker for the affected repositories.
