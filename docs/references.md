# References inspected

Checked on 2026-10-26 through web retrieval. All supplied URLs resolved.
Tutorials inform architecture; none were copied. Installed API signatures and
official documentation take precedence.

Observed redirects: ADK docs now use adk.dev; Google Search docs resolve to
https://adk.dev/integrations/google-search/; MCP Toolbox repository resolves to
https://github.com/googleapis/mcp-toolbox; AlloyDB docs use docs.cloud.google.com.
The Shopify reference identifies Storefront 2026-10 as latest.

Lead research references describe intake, pattern discovery, validation and reports.
The CLI sample describes subprocess tool integration; unrestricted command/file
automation is excluded by our master prompt. Bug, review and commerce references
are preliminary architectural readings and will be rechecked at their gates.

Use these specific assignment references as architectural guidance. Read current versions before implementation and compare with current official API docs. Do not treat an older blog snippet as authoritative over current package documentation.

### A — Lead generation
- Google Cloud: https://cloud.google.com/blog/products/ai-machine-learning/build-a-deep-research-agent-with-google-adk
- Sample: https://github.com/MagnIeeT/leadGenerationAgentADK

### B — Gemini CLI within ADK
- Article: https://medium.com/@derrickchwong/combine-adk-gemini-cli-and-cloud-run-c5dea5118853
- Sample: https://github.com/derrickchwong/gemini-cli-on-adk
- Official Gemini CLI headless docs: https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/headless.md
- Official CLI installation: https://geminicli.com/docs/get-started/installation/

### C — MCP bug assistant
- Google Cloud: https://cloud.google.com/blog/topics/developers-practitioners/tools-make-an-agent-from-zero-to-assistant-with-adk
- Sample: https://github.com/google/adk-samples/tree/main/python/agents/software-bug-assistant
- ADK MCP docs: https://google.github.io/adk-docs/tools-custom/mcp-tools/
- Official GitHub MCP server: https://github.com/github/github-mcp-server

### D — Code review
- Codelab: https://codelabs.developers.google.com/adk-code-reviewer-assistant/instructions?hl=en#0
- Sample: https://github.com/ayoisio/adk-code-review-assistant

### E — E-commerce
- Google codelab: https://codelabs.developers.google.com/codelabs/sports-agent-adk-mcp-alloydb?hl=en#8
- Sample: https://github.com/mtoscano84/sports-agent-adk-mcp-alloydb/
- MCP Toolbox docs/repo: https://github.com/googleapis/genai-toolbox
- AlloyDB docs: https://cloud.google.com/alloydb/docs
- Shopify developer documentation: https://shopify.dev/docs/api/storefront

### Official cross-cutting docs
- ADK docs: https://google.github.io/adk-docs/
- ADK evaluations: https://adk.dev/evaluate/
- Google Search tool for ADK: https://adk.dev/tools/gemini-api/google-search/
- ADK Python implementation: https://github.com/google/adk-python
