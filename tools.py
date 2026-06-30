from __future__ import annotations

from langchain_community.tools import WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper

try:
    from langchain_tavily import TavilySearch
except ImportError:
    from langchain_community.tools.tavily_search import TavilySearchResults as TavilySearch


def build_tools():
    """
    Create the external research tools used by the Deep Research Agent.

    Tools included:
    - Tavily search
      - purpose: search the live web for current or broad information
      - important config: max_results=5
      - typical input: a natural-language search query

    - Wikipedia search
      - purpose: retrieve encyclopedia-style background knowledge
      - typical input: a natural-language topic or entity name

    Returns:
        list: a list of LangChain-compatible tool objects that can be
        bound to an LLM or passed into a ToolNode.
    """

    tavily_search = TavilySearch(
        max_results=5,
        include_answer=True,
        include_raw_content=True,
        include_images=False,
        search_depth="advanced",
    )
    wikipedia_search = WikipediaQueryRun(
        api_wrapper=WikipediaAPIWrapper(top_k_results=3, doc_content_chars_max=1800)
    )

    return [tavily_search, wikipedia_search]
