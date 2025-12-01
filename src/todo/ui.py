"""UI components for AI todo sorter using python-hiccup."""
from python_hiccup.html.core import render as hiccup_render


def layout(content):
    """Base layout with Datastar loaded."""
    return hiccup_render([
        'html', {'lang': 'en'},
        ['head',
            ['meta', {'charset': 'UTF-8'}],
            ['meta', {'name': 'viewport', 'content': 'width=device-width, initial-scale=1.0'}],
            ['title', 'AI Todo Sorter'],
            ['script', {
                'type': 'module',
                'src': 'https://cdn.jsdelivr.net/gh/starfederation/datastar@1.0.0-RC.6/bundles/datastar.js'
            }],
            ['link', {'rel': 'stylesheet', 'href': '/static/css/base.css'}],
            ['link', {'rel': 'stylesheet', 'href': '/static/css/lists.css'}],
            ['style', """
                .ranking-item {
                    transition: all 0.5s ease;
                    margin: 8px 0;
                    padding: 12px;
                    background: #f8f9fa;
                    border-radius: 4px;
                    display: flex;
                    align-items: center;
                    gap: 12px;
                }
                .ranking-item .rank {
                    font-weight: bold;
                    color: #666;
                    min-width: 30px;
                }
                .ranking-item .title {
                    flex: 1;
                }
                .ranking-item .score {
                    color: #999;
                    font-size: 0.9em;
                }
                .thinking {
                    color: #666;
                    font-style: italic;
                    animation: pulse 1.5s infinite;
                    padding: 12px;
                    background: #f0f8ff;
                    border-radius: 4px;
                    margin: 12px 0;
                }
                @keyframes pulse {
                    0% { opacity: 0.5; }
                    50% { opacity: 1; }
                    100% { opacity: 0.5; }
                }
                .vote-log {
                    margin-top: 20px;
                    padding: 12px;
                    background: #fafafa;
                    border-radius: 4px;
                    max-height: 300px;
                    overflow-y: auto;
                }
                .vote-item {
                    font-size: 0.9em;
                    padding: 8px;
                    border-bottom: 1px solid #eee;
                }
                .vote-item:last-child {
                    border-bottom: none;
                }
                .vote-item .items {
                    font-weight: 500;
                    color: #333;
                }
                .vote-item .reason {
                    color: #666;
                    margin-top: 4px;
                }
                .form-group {
                    margin-bottom: 16px;
                }
                .form-group label {
                    display: block;
                    margin-bottom: 4px;
                    font-weight: 500;
                }
                .form-group textarea,
                .form-group input,
                .form-group select {
                    width: 100%;
                    padding: 8px;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    font-family: inherit;
                }
                .form-group textarea {
                    font-family: monospace;
                    resize: vertical;
                }
            """]
        ],
        ['body',
            ['div', {'class': 'back-link'},
                ['a', {'href': '/'}, '← Back to Index']
            ],
            content
        ]
    ])


def create_form(conversations=None):
    """Form to create a new chat session."""
    if conversations is None:
        conversations = []

    # Build conversation list
    conv_list = []
    if conversations:
        conv_list = [
            ['h3', {'style': 'margin-top: 40px; margin-bottom: 10px;'}, 'Recent Conversations'],
            ['ul', {'class': 'email-list', 'style': 'list-style: none; padding: 0;'},
                *[
                    ['li', {'style': 'margin-bottom: 8px;'},
                        ['a', {'href': f"/todo/{conv['id']}", 'style': 'text-decoration: none;'},
                            ['div', {'style': 'padding: 10px; background: #f5f5f5; border-radius: 4px; display: flex; justify-content: space-between;'},
                                ['span', f"Conversation {conv['id'][:8]}... ({conv['item_count']} items)"],
                                ['span', {'style': 'color: #999; font-size: 0.9em;'}, conv['model'].split('/')[-1]]
                            ]
                        ]
                    ] for conv in conversations[:10]  # Show last 10
                ]
            ]
        ]

    return [
        'div', {'class': 'item-card', 'style': 'max-width: 600px; margin: 0 auto; margin-top: 10vh;'},
        ['h1', 'Chat with Sorter'],
        ['p', 'Start a conversation with an AI that thinks in SorterDSL. As you chat, it will help you organize and prioritize your thoughts.'],
        ['div', {
            'data-store': '{"message": "", "model": "anthropic/claude-3.5-haiku"}'
        },
            ['div', {'class': 'form-group'},
                ['label', 'Start the conversation:'],
                ['textarea', {
                    'style': 'height: 120px;',
                    'data-bind': 'message',
                    'placeholder': 'e.g., "I need to plan my weekend", "Help me prioritize my tasks", "Add buy milk and eggs"'
                }, ' ']
            ],
            ['div', {'class': 'form-group'},
                ['label', 'Model:'],
                ['select', {'data-bind': 'model'},
                    ['option', {'value': 'anthropic/claude-3.5-haiku'}, 'Claude 3.5 Haiku'],
                    ['option', {'value': 'openai/gpt-4o-mini'}, 'GPT-4o Mini'],
                    ['option', {'value': 'meta-llama/llama-3.1-70b-instruct'}, 'Llama 3.1 70B'],
                ]
            ],
            ['button', {
                'class': 'button',
                'data-on:click': "@post('/todo/create')",
                'data-attr-disabled': "!$message.trim()"
            }, 'Start Chat']
        ],
        *conv_list
    ]


def ranking_view(list_id, items, meta, vote_log=None, is_streaming=True):
    """View showing ranked items.

    Args:
        list_id: The list identifier
        items: List of (title, score, rank) tuples
        meta: Metadata dict with criteria and model
        vote_log: List of vote dicts with item1, item2, reason
        is_streaming: Whether AI is still sorting
    """
    # Build ranking list
    ranking_items = []
    for title, score, rank in items:
        ranking_items.append([
            'div', {
                'class': 'ranking-item',
                'id': f'item-{title}'
            },
            ['span', {'class': 'rank'}, f'#{rank}'],
            ['span', {'class': 'title'}, title.replace('-', ' ').title()],
            ['span', {'class': 'score'}, f'{score:.3f}']
        ])

    # Build status/control panel
    control_panel = []
    if is_streaming:
        control_panel = [
            'div', {
                'id': 'ai-status',
                'class': 'thinking'
            },
            'AI is analyzing pairs...'
        ]
    else:
        control_panel = [
            'div', {
                'id': 'ai-status',
                'style': 'color: green; font-weight: bold; padding: 12px;'
            },
            '✓ Sorting complete!'
        ]

    # Build vote log
    vote_log_element = []
    if vote_log:
        vote_items = []
        for vote in vote_log:
            vote_items.append([
                'div', {'class': 'vote-item'},
                ['div', {'class': 'items'},
                    f"{vote['item1']} vs {vote['item2']}"
                ],
                ['div', {'class': 'reason'},
                    f"→ {vote['reason']}"
                ]
            ])

        vote_log_element = [
            'div', {'class': 'vote-log', 'id': 'vote-log'},
            ['h3', {'style': 'margin-top: 0'}, 'AI Reasoning'],
            *vote_items
        ]

    # Add SSE trigger as separate element if streaming
    sse_trigger = []
    if is_streaming:
        sse_trigger = [
            ['div', {
                'data-init': f"@get('/todo/{list_id}/stream')",
                'style': 'display:none',
                'id': 'sse-trigger'
            }, ' ']
        ]

    return [
        'div', {'id': 'ranking-container'},
        ['h2', f"Sorting by: {meta['criteria']}"],
        ['p', {'style': 'color: #666'}, f"Model: {meta['model']}"],
        *sse_trigger,  # SSE trigger at top level, not nested
        control_panel,
        ['div', {'id': 'rankings'}, *ranking_items],
        *([vote_log_element] if vote_log_element else [])
    ]


def vote_update_fragment(item1, item2, reason):
    """Fragment for a single vote update (prepended to vote log)."""
    return hiccup_render([
        'div', {
            'class': 'vote-item',
            'id': 'vote-log',
            'data-merge-mode': 'prepend'
        },
        ['div', {'class': 'items'},
            f"{item1} vs {item2}"
        ],
        ['div', {'class': 'reason'},
            f"→ {reason}"
        ]
    ])


def chat_view(list_id, history_hiccup, rankings_hiccup, meta):
    """
    Split view: Chat on left, Rankings on right.

    Args:
        history_hiccup: Hiccup data structure (not HTML string)
        rankings_hiccup: Hiccup data structure (not HTML string)
    """
    return [
        'div', {'class': 'chat-container', 'style': 'display: flex; gap: 20px; height: 85vh;'},

        # Left Panel: Conversation
        ['div', {'class': 'chat-panel', 'style': 'flex: 2; display: flex; flex-direction: column; border-right: 1px solid #ddd; padding-right: 20px;'},
            ['h2', 'Chat with Sorter'],
            ['div', {'id': 'chat-history', 'style': 'flex: 1; overflow-y: auto; padding-bottom: 20px; margin-bottom: 20px;'},
                history_hiccup
            ],

            # Input Area
            ['div', {'class': 'input-area', 'style': 'margin-top: auto;'},
                ['div', {
                    'data-store': '{"message": ""}',
                    'class': 'chat-input-wrapper'
                },
                    ['textarea', {
                        'data-bind': 'message',
                        'placeholder': 'Type a message (e.g., "Add milk and eggs", "I prefer eggs over milk")',
                        'style': 'width: 100%; height: 80px; padding: 10px; font-family: inherit; border: 1px solid #ddd; border-radius: 4px;',
                        'data-on:keydown': "evt.key === 'Enter' && !evt.shiftKey && (evt.preventDefault(), document.getElementById('send-btn').click())"
                    }, ' '],
                    ['div', {'style': 'display: flex; justify-content: space-between; margin-top: 8px;'},
                        ['span', {'style': 'color: #999; font-size: 0.8em;'}, 'AI speaks SorterDSL'],
                        ['button', {
                            'id': 'send-btn',
                            'class': 'button',
                            'data-on:click': f"@post('/todo/{list_id}/chat'); $message=''",
                            'data-attr-disabled': "!$message.trim()"
                        }, 'Send']
                    ]
                ]
            ]
        ],

        # Right Panel: Live State
        ['div', {'class': 'state-panel', 'style': 'flex: 1; overflow-y: auto; background: #fafafa; padding: 15px; border-radius: 8px;'},
            ['h3', {'style': 'margin-top: 0'}, 'Live State'],
            ['div', {'id': 'rankings-view'},
                rankings_hiccup
            ]
        ]
    ]


def message_bubble(role, content_hiccup):
    """Render a single message bubble.

    Args:
        role: "user" or "ai"
        content_hiccup: Hiccup data structure (not HTML string)
    """
    bg_color = "#e3f2fd" if role == "user" else "#f5f5f5"
    align = "flex-end" if role == "user" else "flex-start"

    return hiccup_render([
        'div', {
            'class': f'message {role}',
            'style': f'display: flex; flex-direction: column; align-items: {align}; margin-bottom: 15px;'
        },
        ['div', {
            'style': f'background: {bg_color}; padding: 10px 15px; border-radius: 12px; max-width: 90%; word-wrap: break-word;'
        },
            content_hiccup
        ],
        ['span', {'style': 'font-size: 0.7em; color: #999; margin-top: 4px;'}, role.title()]
    ])


def rankings_fragment(items, meta):
    """Render just the rankings list (returns hiccup data structure)."""
    ranking_items = []

    if not items:
        ranking_items = [['p', {'class': 'no-items', 'style': 'color: #999; font-style: italic;'}, 'Start chatting to define items...']]
    else:
        for title, score, rank in items:
            ranking_items.append([
                'div', {'class': 'ranking-item', 'style': 'margin: 8px 0; padding: 10px; background: white; border-radius: 4px; display: flex; gap: 10px;'},
                ['span', {'class': 'rank', 'style': 'font-weight: bold; color: #666; min-width: 25px;'}, f'#{rank}'],
                ['span', {'class': 'title', 'style': 'flex: 1;'}, title.replace('-', ' ').title()],
                ['span', {'class': 'score', 'style': 'color: #999; font-size: 0.9em;'}, f'{score:.2f}']
            ])

    return [
        'div', {'id': 'rankings-view'},
        ['div', {'style': 'margin-bottom: 10px; font-size: 0.9em; color: #666;'},
            f"Context: {meta.get('criteria', 'general')}"
        ],
        ['div', {'id': 'rankings-list'}, *ranking_items]
    ]
