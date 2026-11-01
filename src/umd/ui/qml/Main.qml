import QtQuick
import QtQuick.Controls
import QtQuick.Window
import "components"

ApplicationWindow {
    id: win
    width: 1440
    height: 900
    minimumWidth: 1024
    minimumHeight: 680
    visible: true
    title: "Universal Media Downloader"
    color: ink.windowBg
    font.family: "Segoe UI Variable Text"
    font.pixelSize: 13

    // Native caption buttons stay with Windows. Do not set FramelessWindowHint.
    flags: Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint
           | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint
           | Qt.WindowCloseButtonHint

    property int sidebarWidth: !shell.sidebarOpen ? 0 : (width < 1100 ? 196 : 236)
    property int inspectorWidth: shell.inspectorOpen ? (width < 1100 ? 265 : 298) : 0
    property int columnCount: width < 1100 ? 3 : 4
    property int toolbarHeight: 60
    property string hostMode: "native-frame"
    property bool motionEnabled: !shell.reduceMotion

    Behavior on sidebarWidth {
        enabled: !shell.reduceMotion
        NumberAnimation { duration: motion.sidebarSelectMs; easing.type: Easing.OutCubic }
    }
    Behavior on inspectorWidth {
        enabled: !shell.reduceMotion
        SpringAnimation {
            spring: motion.inspectorSpring
            damping: motion.inspectorDamping
            mass: motion.inspectorMass
            epsilon: 0.25
        }
    }

    property var urlEditor: null

    Shortcut {
        sequences: ["Ctrl+F"]
        onActivated: if (urlEditor) urlEditor.forceActiveFocus()
    }
    Shortcut {
        sequences: ["Ctrl+A"]
        enabled: !urlEditor || !urlEditor.activeFocus
        onActivated: shell.selectAllVisible()
    }
    Shortcut {
        sequences: ["Esc"]
        onActivated: {
            if (shell.inspectorOpen)
                shell.toggleInspector()
        }
    }
    Column {
        anchors.fill: parent
        spacing: 0

        TopBar {
            width: parent.width
            height: win.toolbarHeight
        }

        Item {
            width: parent.width
            height: parent.height - win.toolbarHeight - 60

            Sidebar {
                id: side
                width: win.sidebarWidth
                height: parent.height
            }
            MediaGrid {
                x: side.width
                width: parent.width - side.width - inspector.width
                height: parent.height
                columnCount: win.columnCount
            }
            InspectorPanel {
                id: inspector
                x: parent.width - width
                width: win.inspectorWidth
                height: parent.height
            }
        }

        StatusStrip {
            width: parent.width
            height: 60
        }
    }

    Rectangle {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 76
        radius: 11
        color: "#24262DE8"
        width: toastText.implicitWidth + 32
        height: shell.toast.length > 0 ? 36 : 0
        opacity: shell.toast.length > 0 ? 1 : 0
        visible: height > 0
        Text {
            id: toastText
            anchors.centerIn: parent
            text: shell.toast
            color: "white"
            font.pixelSize: 12
            font.family: "Segoe UI Variable Text"
        }
        Behavior on opacity {
            enabled: !shell.reduceMotion
            NumberAnimation { duration: motion.buttonHoverMs }
        }
    }
}
