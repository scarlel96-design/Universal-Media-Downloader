import QtQuick
import QtQuick.Controls

Rectangle {
    id: root
    property int columnCount: 4
    color: ink.canvas

    Column {
        id: header
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: root.width < 1100 ? 24 : 35
        anchors.topMargin: 28
        spacing: 12

        Row {
            spacing: 8
            Rectangle { width: 6; height: 6; radius: 3; color: "#26B078"; anchors.verticalCenter: parent.verticalCenter }
            Text {
                text: shell.banner
                color: ink.muted
                font.pixelSize: 11
                font.family: "Segoe UI Variable Text"
            }
        }

        Row {
            width: parent.width
            spacing: 8
            Text {
                text: shell.page
                color: ink.title
                font.pixelSize: root.width < 1100 ? 26 : 30
                font.weight: Font.DemiBold
                font.family: "Segoe UI Variable Text"
                width: parent.width - filters.width - 8
                elide: Text.ElideRight
            }
            Row {
                id: filters
                spacing: 6
                FilterChip { label: "전체"; mode: "all" }
                FilterChip { label: "이미지"; mode: "image" }
                FilterChip { label: "영상"; mode: "video" }
                Rectangle {
                    readonly property bool active: shell.showExcluded
                    width: excludedText.width + 24
                    height: 28
                    radius: 8
                    color: active ? ink.canvas : "transparent"
                    border.color: active ? ink.border : "transparent"
                    Accessible.role: Accessible.Button
                    Accessible.name: "기본 제외 이미지 표시"
                    Accessible.onPressAction: shell.toggleShowExcluded()
                    Text {
                        id: excludedText
                        anchors.centerIn: parent
                        text: "제외 표시"
                        color: active ? ink.title : ink.muted
                        font.pixelSize: 11
                        font.weight: Font.DemiBold
                        font.family: "Segoe UI Variable Text"
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: shell.toggleShowExcluded()
                    }
                }
            }
        }

        Row {
            width: parent.width
            Text {
                text: shell.visibleCount + "개의 미디어"
                color: ink.text
                font.pixelSize: 12
                font.family: "Segoe UI Variable Text"
            }
            Item { width: 12; height: 1 }
            Text {
                text: shell.gridNote
                color: ink.muted
                font.pixelSize: 12
                font.family: "Segoe UI Variable Text"
            }
            Item { width: 12; height: 1 }
            Text {
                text: "전체 선택"
                color: ink.text
                font.pixelSize: 12
                font.family: "Segoe UI Variable Text"
                font.weight: Font.DemiBold
                Accessible.role: Accessible.Button
                Accessible.name: "전체 선택"
                Accessible.onPressAction: shell.selectAllVisible()
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: shell.selectAllVisible()
                }
            }
            Item { width: 8; height: 1 }
            Text {
                text: "선택 해제"
                color: ink.text
                font.pixelSize: 12
                font.family: "Segoe UI Variable Text"
                font.weight: Font.DemiBold
                Accessible.role: Accessible.Button
                Accessible.name: "선택 해제"
                Accessible.onPressAction: shell.clearSelection()
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: shell.clearSelection()
                }
            }
        }

        Column {
            visible: shell.metricsVisible
            width: parent.width
            spacing: 8
            Text {
                width: parent.width
                text: shell.metricsLine
                color: ink.text
                font.pixelSize: 12
                font.family: "Segoe UI Variable Text"
                elide: Text.ElideRight
            }
            Rectangle {
                visible: shell.overallPercent >= 0
                width: parent.width
                height: 4
                radius: 2
                color: ink.border
                Rectangle {
                    width: parent.width * shell.overallPercent / 100
                    height: parent.height
                    radius: 2
                    color: ink.accent
                }
            }
            Row {
                spacing: 6
                ModeChip { label: "안정" }
                ModeChip { label: "균형" }
                ModeChip { label: "고속" }
            }
        }
    }

    GridView {
        id: grid
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.top: header.bottom
        anchors.margins: root.width < 1100 ? 24 : 35
        anchors.topMargin: 16
        model: mediaModel
        cellWidth: Math.floor(width / root.columnCount)
        cellHeight: Math.floor((cellWidth - 13) / 1.15) + 13
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        keyNavigationEnabled: true

        delegate: Item {
            required property string title
            required property string kind
            required property bool selected
            required property int hue
            required property int index
            required property string previewUrl
            required property string classification
            required property string status
            required property real progress
            required property int resumeCapable
            required property string note
            width: grid.cellWidth
            height: grid.cellHeight
            onStatusChanged: {
                if (status !== "완료")
                    return
                if (shell.reduceMotion) {
                    checkMark.pop = 1
                    return
                }
                checkMark.pop = 0.86
                doneSpring.restart()
            }

            Rectangle {
                anchors.fill: parent
                anchors.margins: 6
                radius: 12
                clip: true
                color: Qt.hsla(hue / 360, 0.45, shell.theme === "dark" ? 0.35 : 0.62, 1)
                border.color: selected ? ink.accent : "transparent"
                border.width: 2
                scale: cardArea.containsMouse && !shell.reduceMotion ? 1.015 : 1
                Accessible.role: Accessible.CheckBox
                Accessible.name: title + (kind === "video" ? " 영상" : " 이미지")
                Accessible.checkable: true
                Accessible.checked: selected

                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: parent.height * 0.42
                    radius: 12
                    color: Qt.hsla(((hue + 40) % 360) / 360, 0.35, shell.theme === "dark" ? 0.22 : 0.42, 1)
                }

                Image {
                    anchors.fill: parent
                    visible: previewUrl.length > 0
                    asynchronous: true
                    cache: true
                    fillMode: Image.PreserveAspectCrop
                    source: previewUrl.length > 0 ? previewUrl : ""
                    sourceSize.width: 480
                    sourceSize.height: 480
                }

                Rectangle {
                    visible: classification === "excluded" || classification === "uncertain"
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.margins: 10
                    width: mark.implicitWidth + 12
                    height: 20
                    radius: 6
                    color: classification === "excluded" ? "#8A3A3AD0" : "#8A6A2AD0"
                    Text {
                        id: mark
                        anchors.centerIn: parent
                        text: classification === "excluded" ? "제외" : "불확실"
                        color: "white"
                        font.pixelSize: 10
                        font.family: "Segoe UI Variable Text"
                    }
                }

                Text {
                    visible: status !== "" && status !== "대기"
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.topMargin: classification === "excluded" || classification === "uncertain" ? 34 : 10
                    anchors.leftMargin: 10
                    text: {
                        if (note.length > 0)
                            return status + " · " + note
                        if (resumeCapable === 0 && status === "완료")
                            return "완료 · 재개 불가"
                        return status
                    }
                    color: "white"
                    font.pixelSize: 10
                    font.family: "Segoe UI Variable Text"
                }

                Rectangle {
                    visible: status === "다운로드 중" && progress >= 0
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: 3
                    color: "#FFFFFF55"
                    Rectangle {
                        width: parent.width * Math.max(0, Math.min(1, progress))
                        height: parent.height
                        color: "white"
                    }
                }

                Text {
                    anchors.left: parent.left
                    anchors.bottom: parent.bottom
                    anchors.margins: 10
                    text: title
                    color: "white"
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                    font.family: "Segoe UI Variable Text"
                    opacity: cardArea.containsMouse || selected ? 1 : 0
                    Behavior on opacity {
                        enabled: !shell.reduceMotion
                        NumberAnimation { duration: motion.gridSelectMs }
                    }
                }

                Rectangle {
                    id: checkMark
                    property real pop: 1
                    width: 22
                    height: 22
                    radius: 11
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 10
                    color: selected ? ink.accent : "#FFFFFFB8"
                    border.color: "white"
                    opacity: cardArea.containsMouse || selected ? 1 : 0
                    scale: pop
                    SpringAnimation {
                        id: doneSpring
                        target: checkMark
                        property: "pop"
                        to: 1
                        spring: motion.successSpring
                        damping: motion.successDamping
                        mass: motion.successMass
                    }
                    Text {
                        anchors.centerIn: parent
                        text: selected ? "✓" : ""
                        color: "white"
                        font.pixelSize: 12
                    }
                    Behavior on opacity {
                        enabled: !shell.reduceMotion
                        NumberAnimation { duration: motion.gridSelectMs }
                    }
                }

                Text {
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 12
                    visible: kind === "video" && !selected && !cardArea.containsMouse
                    text: "영상"
                    color: "white"
                    font.pixelSize: 10
                    font.family: "Segoe UI Variable Text"
                }

                MouseArea {
                    id: cardArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: shell.activate(index)
                }
                Behavior on scale {
                    enabled: !shell.reduceMotion
                    NumberAnimation { duration: motion.buttonHoverMs }
                }
            }
        }
    }

    component ModeChip: Rectangle {
        property string label: ""
        readonly property bool active: shell.downloadMode === label
        width: modeText.width + 20
        height: 26
        radius: 8
        color: active ? ink.accent : "transparent"
        border.color: active ? ink.accent : ink.border
        Accessible.role: Accessible.Button
        Accessible.name: label + " 다운로드 모드"
        Accessible.onPressAction: shell.setDownloadMode(label)
        Text {
            id: modeText
            anchors.centerIn: parent
            text: label
            color: active ? "white" : ink.text
            font.pixelSize: 11
            font.family: "Segoe UI Variable Text"
        }
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: shell.setDownloadMode(label)
        }
    }

    component FilterChip: Rectangle {
        property string label: ""
        property string mode: "all"
        readonly property bool active: shell.filterMode === mode
        width: labelText.width + 24
        height: 28
        radius: 8
        color: active ? ink.canvas : "transparent"
        border.color: active ? ink.border : "transparent"
        Accessible.role: Accessible.Button
        Accessible.name: label + " 필터"
        Accessible.onPressAction: shell.setFilter(mode)

        Text {
            id: labelText
            anchors.centerIn: parent
            text: label
            color: active ? ink.title : ink.muted
            font.pixelSize: 11
            font.weight: Font.DemiBold
            font.family: "Segoe UI Variable Text"
        }
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: shell.setFilter(mode)
        }
    }
}
