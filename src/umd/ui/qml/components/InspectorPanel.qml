import QtQuick

Rectangle {
    id: root
    color: ink.inspectorBg
    clip: true

    Rectangle {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: root.width > 0 ? 1 : 0
        color: ink.border
    }

    Column {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.margins: 20
        width: 258
        spacing: 12
        visible: root.width > 40

        Text {
            text: "미디어 정보"
            color: ink.title
            font.pixelSize: 14
            font.weight: Font.DemiBold
            font.family: "Segoe UI Variable Text"
        }

        Rectangle {
            width: parent.width
            height: 168
            radius: 12
            clip: true
            color: Qt.hsla(shell.detailHue / 360, 0.45, shell.theme === "dark" ? 0.35 : 0.62, 1)
            Image {
                anchors.fill: parent
                visible: shell.detailPreview.length > 0
                asynchronous: true
                cache: true
                fillMode: Image.PreserveAspectCrop
                source: shell.detailPreview.length > 0 ? shell.detailPreview : ""
                sourceSize.width: 640
                sourceSize.height: 640
            }
        }

        Text {
            text: shell.detailTitle
            color: ink.title
            font.pixelSize: 14
            font.weight: Font.DemiBold
            font.family: "Segoe UI Variable Text"
            width: parent.width
            elide: Text.ElideRight
        }

        Grid {
            columns: 2
            columnSpacing: 8
            rowSpacing: 10
            Text { text: "형식"; color: ink.muted; font.pixelSize: 11; font.family: "Segoe UI Variable Text"; width: 90 }
            Text { text: shell.detailKind; color: ink.text; font.pixelSize: 11; font.family: "Segoe UI Variable Text"; width: 150 }
            Text { text: "원본 주소"; color: ink.muted; font.pixelSize: 11; font.family: "Segoe UI Variable Text"; width: 90 }
            Text {
                text: shell.detailSource
                color: ink.text
                font.pixelSize: 11
                font.family: "Segoe UI Variable Text"
                width: 150
                elide: Text.ElideMiddle
            }
            Text { text: "게시물 관련성"; color: ink.muted; font.pixelSize: 11; font.family: "Segoe UI Variable Text"; width: 90 }
            Text {
                text: shell.detailRelevance
                color: ink.text
                font.pixelSize: 11
                font.family: "Segoe UI Variable Text"
                width: 150
                elide: Text.ElideRight
            }
            Text { text: "저장 상태"; color: ink.muted; font.pixelSize: 11; font.family: "Segoe UI Variable Text"; width: 90 }
            Text {
                text: shell.detailStatus
                color: ink.text
                font.pixelSize: 11
                font.family: "Segoe UI Variable Text"
                width: 150
                elide: Text.ElideRight
            }
        }
        Text {
            visible: shell.detailProgress.length > 0
            width: parent.width
            text: shell.detailProgress
            color: ink.muted
            font.pixelSize: 11
            font.family: "Segoe UI Variable Text"
            elide: Text.ElideRight
        }
        Text {
            visible: shell.detailReasons.length > 0
            text: shell.detailReasons
            color: ink.muted
            font.pixelSize: 11
            font.family: "Segoe UI Variable Text"
            width: parent.width
            wrapMode: Text.WordWrap
        }
    }
}
