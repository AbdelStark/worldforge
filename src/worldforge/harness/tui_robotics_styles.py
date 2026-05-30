"""Textual-free CSS constants for the robotics showcase report."""

from __future__ import annotations

ROBOTICS_TABLETOP_HELP_SCREEN_CSS = """
    RoboticsTabletopHelpScreen {
        align: center middle;
    }

    RoboticsTabletopHelpScreen > #robotics-help-card {
        width: 104;
        height: 38;
        background: $surface;
        border: tall $accent;
        padding: 1 2;
    }

    RoboticsTabletopHelpScreen #robotics-help-title {
        height: 1;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    RoboticsTabletopHelpScreen .robotics-help-section {
        margin-bottom: 1;
    }
    """

ROBOTICS_SHOWCASE_APP_CSS = """
    Header {
        background: $surface;
        color: $foreground;
    }

    Footer {
        background: $surface;
        color: $foreground;
    }

    #robotics-body {
        height: 1fr;
        padding: 1 2;
        background: $surface;
    }

    RoboticsHeroPane {
        height: 10;
        margin-bottom: 1;
    }

    RoboticsProgressPane {
        height: 5;
        margin-bottom: 1;
    }

    RoboticsPipelinePane {
        height: 13;
        margin-bottom: 1;
    }

    RoboticsReportGuidePane {
        height: 11;
        margin-bottom: 1;
    }

    RoboticsRerunPane {
        height: 9;
        margin-bottom: 1;
    }

    RoboticsTensorBoardPane {
        height: 11;
        margin-bottom: 1;
    }

    RoboticsMetricsPane {
        height: 12;
        margin-bottom: 1;
    }

    RoboticsArmPane {
        height: 15;
        margin-bottom: 1;
    }

    RoboticsCandidatePane {
        height: 10;
        margin-bottom: 1;
    }

    RoboticsTabletopPane {
        height: 17;
        margin-bottom: 1;
    }

    RoboticsEventPane {
        height: 10;
        margin-bottom: 1;
    }
    """
