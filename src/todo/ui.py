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


def create_form():
    """Form to create a new todo list."""
    return [
        'div', {'class': 'item-card', 'style': 'max-width: 600px; margin: 0 auto;'},
        ['h1', 'AI Todo Sorter'],
        ['p', 'Paste your todo list, define a criteria, and watch AI rank it live.'],
        ['div', {
            'data-store': '{"items": "", "criteria": "Urgency", "model": "anthropic/claude-3.5-haiku"}'
        },
            ['div', {'class': 'form-group'},
                ['label', 'Items (one per line):'],
                # Note: textarea needs content (even if empty string won't work in hiccup)
                # Using a comment or space to force proper closing tag
                ['textarea', {
                    'style': 'height: 150px;',
                    'data-bind': 'items',
                    'placeholder': 'Fix critical bug, Write documentation, Refactor code, ...'
                }, ' ']  # Space to force closing tag
            ],
            ['div', {'class': 'form-group'},
                ['label', 'Sorting Criteria:'],
                ['input', {
                    'type': 'text',
                    'data-bind': 'criteria',
                    'placeholder': 'e.g., Urgency, Difficulty, Impact'
                }]
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
                'data-attr-disabled': "!$items.trim()"
            }, 'Start Sorting']
        ]
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
