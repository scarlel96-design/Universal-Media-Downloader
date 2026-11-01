import QtQuick

Rectangle {
    id: root
    color: ink.statusBg

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 1
        color: ink.border
    }

    Row {
        anchors.fill: parent
        anchors.leftMargin: 28
        anchors.rightMargin: 20
        spacing: 14

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: shell.selectedCount + "개 선택됨"
            color: ink.text
            font.pixelSize: 12
            font.family: "Segoe UI Variable Text"
            font.weight: Font.DemiBold
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: shell.statusLine
            color: ink.muted
            font.pixelSize: 11
            font.family: "Segoe UI Variable Text"
        }
        Item { width: Math.max(12, root.width - 620); height: 1 }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: shell.reduceMotion ? "동작 줄이기 켜짐" : "동작 줄이기 꺼짐"
            color: ink.muted
            font.pixelSize: 11
            font.family: "Segoe UI Variable Text"
        }
        Rectangle {
            width: motionToggle.implicitWidth + 16
            height: 26
            radius: 8
            color: area.containsMouse ? ink.hover : "transparent"
            anchors.verticalCenter: parent.verticalCenter
            border.color: activeFocus ? ink.accent : "transparent"
            border.width: 2
            activeFocusOnTab: true
            Accessible.role: Accessible.Button
            Accessible.name: "동작 줄이기"
            Accessible.onPressAction: shell.toggleReduceMotion()
            Text {
                id: motionToggle
                anchors.centerIn: parent
                text: "모션"
                color: ink.text
                font.pixelSize: 11
                font.family: "Segoe UI Variable Text"
            }
            MouseArea {
                id: area
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: shell.toggleReduceMotion()
            }
        }
        Rectangle {
            width: themeLabel.implicitWidth + 16
            height: 26
            radius: 8
            color: themeArea.containsMouse ? ink.hover : "transparent"
            anchors.verticalCenter: parent.verticalCenter
            activeFocusOnTab: true
            border.color: activeFocus ? ink.accent : "transparent"
            border.width: 2
            Accessible.role: Accessible.Button
            Accessible.name: "테마 전환"
            Accessible.onPressAction: shell.toggleTheme()
            Text {
                id: themeLabel
                anchors.centerIn: parent
                text: shell.theme === "dark" ? "라이트" : "다크"
                color: ink.text
                font.pixelSize: 11
                font.family: "Segoe UI Variable Text"
            }
            MouseArea {
                id: themeArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: shell.toggleTheme()
            }
        }
        Rectangle {
            readonly property bool busy: shell.jobPhase === "다운로드 중" || shell.jobPhase === "일시정지"
            visible: busy
            width: pauseLabel.implicitWidth + 20
            height: 34
            radius: 10
            color: ink.hover
            anchors.verticalCenter: parent.verticalCenter
            activeFocusOnTab: true
            Accessible.role: Accessible.Button
            Accessible.name: shell.jobPhase === "일시정지" ? "다운로드 재개" : "다운로드 일시정지"
            Accessible.onPressAction: shell.jobPhase === "일시정지" ? shell.resumeDownload() : shell.pauseDownload()
            Text {
                id: pauseLabel
                anchors.centerIn: parent
                text: shell.jobPhase === "일시정지" ? "재개" : "일시정지"
                color: ink.text
                font.pixelSize: 12
                font.family: "Segoe UI Variable Text"
            }
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: shell.jobPhase === "일시정지" ? shell.resumeDownload() : shell.pauseDownload()
            }
        }
        Rectangle {
            visible: shell.failedCount > 0 && shell.jobPhase !== "다운로드 중" && shell.jobPhase !== "일시정지"
            width: retryLabel.implicitWidth + 20
            height: 34
            radius: 10
            color: ink.hover
            anchors.verticalCenter: parent.verticalCenter
            Accessible.role: Accessible.Button
            Accessible.name: "실패 항목 재시도"
            Accessible.onPressAction: shell.retryFailed()
            Text {
                id: retryLabel
                anchors.centerIn: parent
                text: "실패 재시도"
                color: ink.text
                font.pixelSize: 12
                font.family: "Segoe UI Variable Text"
            }
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: shell.retryFailed()
            }
        }
        Rectangle {
            readonly property bool busy: shell.jobPhase === "다운로드 중" || shell.jobPhase === "일시정지"
            width: 108
            height: 34
            radius: 10
            color: !busy && shell.selectedCount === 0 ? Qt.rgba(0, 0.48, 1, 0.45) : ink.accent
            anchors.verticalCenter: parent.verticalCenter
            activeFocusOnTab: true
            border.color: activeFocus ? ink.title : "transparent"
            border.width: 2
            Accessible.role: Accessible.Button
            Accessible.name: busy ? "다운로드 취소" : "다운로드"
            Accessible.onPressAction: busy ? shell.cancelDownload() : shell.download()
            Text {
                anchors.centerIn: parent
                text: busy ? "취소" : "다운로드"
                color: "white"
                font.pixelSize: 12
                font.weight: Font.DemiBold
                font.family: "Segoe UI Variable Text"
            }
            MouseArea {
                anchors.fill: parent
                cursorShape: !busy && shell.selectedCount === 0 ? Qt.ForbiddenCursor : Qt.PointingHandCursor
                onClicked: busy ? shell.cancelDownload() : shell.download()
            }
        }
    }
}
