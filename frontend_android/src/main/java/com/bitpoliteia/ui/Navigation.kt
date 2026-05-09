package com.bitpoliteia.ui

sealed class Screen(val route: String) {
    object Onboarding : Screen("onboarding")
    object Main : Screen("main")
}

sealed class BottomNavItem(val route: String, val title: String, val icon: String) {
    object Messages : BottomNavItem("messages", "消息", "chat")
    object Contacts : BottomNavItem("contacts", "通讯录", "contacts")
    object Archives : BottomNavItem("archives", "存档", "archive")
    object Profile : BottomNavItem("profile", "其它", "person")
}
