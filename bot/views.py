import traceback

from core.loggers import log_tasks


async def register_persistent_views(client) -> None:
    from cogs.config_management import ConfigManagement
    from managers.milestones import MilestonesManager
    from ui.all_time_leaderboard import AllTimeLeaderboardView
    from ui.dm_games_view import (
        DMGamesView,
        Start2048View,
        StartConnectFourView,
        StartMemoryView,
        StartMinesweeperView,
        StartTicTacToeView,
        StartWordleView,
    )
    from ui.sendgames_view import ViewMore
    from ui.views.chat_game_admin_view import ChatGameAdminView
    from ui.views.chat_games_manage_view import ChatGamesManageView
    from ui.views.chat_games_view import ChatGamesView
    from ui.views.config_manager_view import ConfigManagerView
    from ui.views.config_viewer_modal import ConfigViewer
    from ui.views.d_m_games_manage_view import DMGamesManageView
    from ui.views.d_m_games_manager_view import DMGamesManagerView
    from ui.views.logs_view import LogsView
    from ui.views.main_game_manager_view import MainGameManagerView
    from ui.views.milestones_view import MilestonesView
    from ui.views.statistics_view import StatisticsView
    from ui.paginator import Paginator

    class DummyInteraction:
        def __init__(self):
            self.user = None

    dummy_interaction = DummyInteraction()

    game_options = ["wordle", "tictactoe", "memory", "connect four", "2048", "minesweeper"]
    for game in game_options:
        client.add_view(DMGamesView(client, game))

    client.add_view(StartWordleView(dummy_interaction, client))
    client.add_view(StartTicTacToeView(dummy_interaction, client))
    client.add_view(StartMemoryView(dummy_interaction, client))
    client.add_view(StartConnectFourView(dummy_interaction, client))
    client.add_view(Start2048View(dummy_interaction, client))
    client.add_view(StartMinesweeperView(dummy_interaction, client))

    client.add_view(ViewMore())

    guild = client.guilds[0] if client.guilds else None
    if guild:
        client.add_view(AllTimeLeaderboardView(client, guild))

    if client.game_manager:
        try:
            client.add_view(MainGameManagerView(client.game_manager, client.config))
            client.add_view(ChatGamesView(client.game_manager, client.config, client))
            client.add_view(ChatGamesManageView(client.game_manager, client.config, client))
            client.add_view(DMGamesManagerView(client.game_manager, client.config, client))
            client.add_view(DMGamesManageView(client.game_manager, client.config, client))
        except Exception as e:
            log_tasks.error(f"Failed to register game manager views: {e}")
            log_tasks.error(traceback.format_exc())

    try:
        temp_cog = ConfigManagement(client)
        available_configs = temp_cog._get_available_configs()
        client.add_view(ConfigManagerView(client.config, available_configs))
    except Exception as e:
        log_tasks.error(f"Failed to register ConfigManagerView: {e}")
        log_tasks.error(traceback.format_exc())

    try:
        client.add_view(ConfigViewer(client.config, "", {}, []))
    except Exception as e:
        log_tasks.error(f"Failed to register ConfigViewer: {e}")

    try:
        client.add_view(LogsView(client, client.config))
    except Exception as e:
        log_tasks.error(f"Failed to register LogsView: {e}")

    try:
        milestones_manager = MilestonesManager()
        client.add_view(MilestonesView(client, client.config, 0, milestones_manager))
    except Exception as e:
        log_tasks.error(f"Failed to register MilestonesView: {e}")

    try:
        client.add_view(StatisticsView(client, client.config, 0))
    except Exception as e:
        log_tasks.error(f"Failed to register StatisticsView: {e}")

    try:
        client.add_view(Paginator())
    except Exception as e:
        log_tasks.error(f"Failed to register Paginator: {e}")

    try:

        class DummyMessage:
            id = 0

        client.add_view(ChatGameAdminView(DummyMessage(), "", None, client, client.config))
    except Exception as e:
        log_tasks.error(f"Failed to register ChatGameAdminView: {e}")

    log_tasks.info("Registered all persistent views")
