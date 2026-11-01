import QtQuick
import QtQuick.Layouts
import QtQuick.Window

Rectangle {
    id: root
    color: ink.toolbar

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 1
        color: ink.border
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 16
        anchors.rightMargin: 12
        spacing: 10

        Row {
            visible: shell.sidebarOpen
            spacing: 10
            Layout.preferredWidth: shell.sidebarOpen ? 200 : 0
            Layout.alignment: Qt.AlignVCenter

            Rectangle {
                width: 27
                height: 27
                radius: 8
                anchors.verticalCenter: parent.verticalCenter
                gradient: Gradient {
                    GradientStop { position: 0.0; color: "#75B2FF" }
                    GradientStop { position: 1.0; color: "#235CCA" }
                }
                Text {
                    anchors.centerIn: parent
                    text: "↓"
                    color: "white"
                    font.pixelSize: 14
                    font.bold: true
                }
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: "Media Downloader"
                color: ink.title
                font.pixelSize: 13
                font.weight: Font.DemiBold
                font.family: "Segoe UI Variable Text"
            }
        }

        Rectangle {
            Layout.preferredWidth: 1
            Layout.fillHeight: true
            color: ink.border
            visible: shell.sidebarOpen
        }

        Row {
            spacing: 2
            Layout.alignment: Qt.AlignVCenter
            IconButton { iconName: "back"; accessibleName: "뒤로"; onTriggered: shell.setPage(shell.page) }
            IconButton { iconName: "forward"; accessibleName: "앞으로"; onTriggered: shell.setPage(shell.page) }
            IconButton { iconName: "sidebar"; accessibleName: "사이드바 펼치기 또는 접기"; onTriggered: shell.toggleSidebar() }
        }

        Text {
            text: shell.page
            color: ink.title
            font.pixelSize: 14
            font.weight: Font.DemiBold
            font.family: "Segoe UI Variable Text"
            Layout.alignment: Qt.AlignVCenter
            elide: Text.ElideRight
            Layout.maximumWidth: 180
        }

        Rectangle {
            id: urlField
            Layout.fillWidth: true
            Layout.minimumWidth: 160
            Layout.maximumWidth: 460
            Layout.preferredHeight: 32
            Layout.alignment: Qt.AlignVCenter
            radius: 10
            color: urlInput.activeFocus ? ink.canvas : ink.field
            border.color: urlInput.activeFocus ? "#8BBAE9" : "transparent"
            border.width: 1

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 8
                spacing: 8
                Icon {
                    name: "link"
                    strokeColor: ink.muted
                    Layout.alignment: Qt.AlignVCenter
                }
                Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 28
                    Text {
                        anchors.fill: parent
                        anchors.leftMargin: 0
                        verticalAlignment: Text.AlignVCenter
                        visible: urlInput.text.length === 0 && !urlInput.activeFocus
                        text: "URL 붙여넣기 · 분석"
                        color: ink.muted
                        font.pixelSize: 12
                        font.family: "Segoe UI Variable Text"
                    }
                    TextInput {
                        id: urlInput
                        anchors.fill: parent
                        verticalAlignment: Text.AlignVCenter
                        clip: true
                        color: ink.text
                        font.pixelSize: 12
                        font.family: "Segoe UI Variable Text"
                        selectByMouse: true
                        objectName: "urlField"
                        Accessible.name: "미디어 주소"
                        Component.onCompleted: Window.window.urlEditor = urlInput
                        text: shell.url
                        onTextChanged: if (text !== shell.url) shell.setUrl(text)
                        onAccepted: shell.analyze()
                        Keys.onEscapePressed: focus = false
                    }
                }
            }
        }

        IconButton {
            iconName: "info"
            accessibleName: "정보 패널"
            onTriggered: shell.toggleInspector()
        }
    }

    component IconButton: Rectangle {
        property string iconName: "home"
        property string accessibleName: ""
        signal triggered()
        width: 30
        height: 30
        Layout.preferredWidth: 30
        Layout.preferredHeight: 30
        Layout.alignment: Qt.AlignVCenter
        radius: 9
        color: area.containsMouse ? ink.hover : "transparent"
        Accessible.role: Accessible.Button
        Accessible.name: accessibleName
        Accessible.onPressAction: triggered()
        activeFocusOnTab: true
        border.color: activeFocus ? ink.accent : "transparent"
        border.width: activeFocus ? 2 : 0

        Icon {
            anchors.centerIn: parent
            name: iconName
            strokeColor: ink.muted
        }
        MouseArea {
            id: area
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: parent.triggered()
        }
        Behavior on color {
            enabled: !shell.reduceMotion
            ColorAnimation { duration: motion.buttonHoverMs }
        }
    }
}
