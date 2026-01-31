package com.bitpoliteia.ui.main

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Email
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.Person
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.bitpoliteia.ui.BottomNavItem
import com.bitpoliteia.ui.ChatScreen
import com.bitpoliteia.ui.contacts.ContactsScreen
import com.bitpoliteia.ui.archives.ArchivesScreen
import com.bitpoliteia.ui.profile.ProfileScreen

@Composable
fun MainScreen() {
    val navController = rememberNavController()
    val bottomNavItems = listOf(
        BottomNavItem.Messages,
        BottomNavItem.Contacts,
        BottomNavItem.Archives,
        BottomNavItem.Profile
    )

    Scaffold(
        bottomBar = {
            NavigationBar {
                val navBackStackEntry by navController.currentBackStackEntryAsState()
                val currentRoute = navBackStackEntry?.destination?.route

                bottomNavItems.forEach { item ->
                    NavigationBarItem(
                        icon = { Icon(getContentIcon(item.route), contentDescription = item.title) },
                        label = { Text(item.title) },
                        selected = currentRoute == item.route,
                        onClick = {
                            navController.navigate(item.route) {
                                popUpTo(navController.graph.findStartDestination().id) {
                                    saveState = true
                                }
                                launchSingleTop = true
                                restoreState = true
                            }
                        }
                    )
                }
            }
        }
    ) { innerPadding ->
        NavHost(
            navController = navController,
            startDestination = BottomNavItem.Messages.route,
            modifier = Modifier.padding(innerPadding)
        ) {
            composable(BottomNavItem.Messages.route) { ChatScreen() }
            composable(BottomNavItem.Contacts.route) { ContactsScreen() }
            composable(BottomNavItem.Archives.route) { ArchivesScreen() }
            composable(BottomNavItem.Profile.route) { ProfileScreen() }
        }
    }
}

fun getContentIcon(route: String) = when(route) {
    "messages" -> Icons.Default.Email
    "contacts" -> Icons.Default.Person
    "archives" -> Icons.Default.List
    else -> Icons.Default.Info
}
