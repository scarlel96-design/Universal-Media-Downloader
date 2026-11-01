import QtQuick
import QtQuick.Controls

Rectangle {
    id: root
    color: ink.sidebar
    clip: true

    Rectangle {
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: 1
        color: ink.border
    }

    Column {
        id: nav
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 12
        spacing: 2

        Text {
            text: "라이브러리"
            color: ink.muted
            font.pixelSize: 10
            font.weight: Font.DemiBold
            font.family: "Segoe UI Variable Text"
            leftPadding: 12
            bottomPadding: 6
        }

        NavRow { label: "전체 미디어"; page: "미디어 보관함"; iconName: "home" }
        NavRow { label: "다운로드"; page: "다운로드"; iconName: "download" }
        NavRow { label: "최근 항목"; page: "최근 항목"; iconName: "clock" }
        NavRow { label: "저장된 콘텐츠"; page: "저장된 콘텐츠"; iconName: "folder" }

        Item { width: 1; height: 18 }

        Text {
            text: "연결된 서비스"
            color: ink.muted
            font.pixelSize: 10
            font.weight: Font.DemiBold
            font.family: "Segoe UI Variable Text"
            leftPadding: 12
            bottomPadding: 6
        }

        NavRow { label: "재생목록"; page: "재생목록"; iconName: "video" }
        NavRow { label: "설정"; page: "설정"; iconName: "settings" }
    }

    Column {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 16
        spacing: 8
        visible: root.width > 80

        Row {
            width: parent.width
            Text { text: "저장 공간"; color: ink.muted; font.pixelSize: 11; font.family: "Segoe UI Variable Text" }
            Item { width: parent.width - 70; height: 1 }
            Text { text: "34%"; color: ink.muted; font.pixelSize: 11; font.family: "Segoe UI Variable Text" }
        }
        Rectangle {
            width: parent.width
            height: 5
            radius: 3
            color: shell.theme === "dark" ? "#434551" : "#E3E4E9"
            Rectangle {
                width: parent.width * 0.34
                height: parent.height
                radius: 3
                color: "#67A9FE"
            }
        }
        Text {
            text: "디자인 전용 예시 데이터"
            color: ink.muted
            font.pixelSize: 10
            font.family: "Segoe UI Variable Text"
        }
    }

    component NavRow: Rectangle {
        property string label: ""
        property string page: ""
        property string iconName: "home"
        readonly property bool active: shell.page === page
        width: parent.width
        height: 34
        radius: 9
        color: active ? (shell.theme === "dark" ? "#285EA348" : "#1473F820") : (area.containsMouse ? ink.hover : "transparent")
        Accessible.role: Accessible.Button
        Accessible.name: label
        Accessible.onPressAction: shell.setPage(page)
        activeFocusOnTab: true
        border.color: activeFocus ? ink.accent : "transparent"
        border.width: activeFocus ? 2 : 0

        Row {
            anchors.fill: parent
            anchors.leftMargin: 12
            spacing: 12
            Icon {
                name: iconName
                strokeColor: active ? ink.accentText : ink.muted
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                text: label
                color: active ? ink.accentText : ink.text
                font.pixelSize: 13
                font.weight: active ? Font.DemiBold : Font.Medium
                font.family: "Segoe UI Variable Text"
                anchors.verticalCenter: parent.verticalCenter
                elide: Text.ElideRight
                width: parent.width - 40
            }
        }
        MouseArea {
            id: area
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: shell.setPage(page)
        }
        Behavior on color {
            enabled: !shell.reduceMotion
            ColorAnimation { duration: motion.sidebarSelectMs }
        }
    }
}
