"""LangGraph agent workflow definition and compilation."""

from functools import partial

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.orm import Session

from app.agent.nodes import (
    classify_intent_node,
    execute_tool_node,
    load_context_node,
    normal_llm_node,
    rag_node,
    synthesize_tool_response_node,
)
from app.agent.router import route_intent
from app.agent.state import AgentState
from app.llm.base import BaseLLMProvider
from app.rag.retriever import DocumentRetriever
from app.tools.base import ToolRegistry


def build_agent_graph(
    llm_provider: BaseLLMProvider,
    tool_registry: ToolRegistry,
    db: Session,
    max_retries: int = 2,
    retriever: DocumentRetriever | None = None,
) -> CompiledStateGraph:
    """Build and compile the multi-step LangGraph agent workflow.

    Workflow topology:
    START
      ↓
    load_context
      ↓
    classify_intent
      ↓ (conditional)
      ├── database_query -> execute_tool -> synthesize_tool_response -> END
      ├── document_search -> rag_node ---------------------------------> END
      └── general_chat   -> normal_llm   ----------------------------> END
    """
    workflow = StateGraph(AgentState)

    # Bind dependencies to node functions
    workflow.add_node("load_context", partial(load_context_node, db=db))
    workflow.add_node(
        "classify_intent",
        partial(classify_intent_node, llm_provider=llm_provider),
    )
    workflow.add_node(
        "normal_llm",
        partial(
            normal_llm_node,
            llm_provider=llm_provider,
            max_retries=max_retries,
        ),
    )
    workflow.add_node(
        "execute_tool",
        partial(execute_tool_node, tool_registry=tool_registry, db=db),
    )
    workflow.add_node(
        "synthesize_tool_response",
        partial(synthesize_tool_response_node, llm_provider=llm_provider),
    )
    workflow.add_node(
        "rag_node",
        partial(
            rag_node,
            llm_provider=llm_provider,
            retriever=retriever,
            db=db,
        ),
    )

    # Construct directed edges
    workflow.add_edge(START, "load_context")
    workflow.add_edge("load_context", "classify_intent")
    workflow.add_conditional_edges(
        "classify_intent",
        route_intent,
        {
            "execute_tool": "execute_tool",
            "normal_llm": "normal_llm",
            "rag_node": "rag_node",
        },
    )
    workflow.add_edge("execute_tool", "synthesize_tool_response")
    workflow.add_edge("synthesize_tool_response", END)
    workflow.add_edge("normal_llm", END)
    workflow.add_edge("rag_node", END)

    return workflow.compile()
