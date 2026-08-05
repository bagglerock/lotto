from __future__ import annotations


def match_distribution_chart_spec() -> dict:
    return {
        "height": 360,
        "encoding": {
            "x": {
                "field": "Number of matches",
                "type": "ordinal",
                "axis": {"title": "Number of matches", "labelAngle": 0},
            },
            "y": {
                "field": "Number of tickets",
                "type": "quantitative",
                "scale": {"type": "symlog", "constant": 1},
                "axis": {"title": "Number of tickets", "format": "~s"},
            },
        },
        "layer": [
            {
                "mark": {
                    "type": "bar",
                    "color": "#E05260",
                    "cornerRadiusTopLeft": 4,
                    "cornerRadiusTopRight": 4,
                },
                "encoding": {
                    "tooltip": [
                        {"field": "Number of matches", "type": "ordinal"},
                        {
                            "field": "Number of tickets",
                            "type": "quantitative",
                            "format": ",",
                        },
                    ]
                },
            },
            {
                "mark": {"type": "text", "dy": -8, "fontWeight": "bold"},
                "encoding": {
                    "text": {
                        "field": "Number of tickets",
                        "type": "quantitative",
                        "format": ",",
                    }
                },
            },
        ],
    }
