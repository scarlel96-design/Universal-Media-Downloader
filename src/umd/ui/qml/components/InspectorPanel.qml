import QtQuick
import QtMultimedia

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
            id: previewFrame
            width: parent.width
            height: 168
            radius: 12
            clip: true
            color: Qt.hsla(shell.detailHue / 360, 0.45, shell.theme === "dark" ? 0.35 : 0.62, 1)
            Image {
                anchors.fill: parent
                visible: shell.detailPreview.length > 0 && !shell.detailIsVideo
                asynchronous: true
                cache: true
                fillMode: Image.PreserveAspectFit
                source: shell.detailPreview.length > 0 ? shell.detailPreview : ""
                sourceSize.width: 640
                sourceSize.height: 640
                opacity: shell.reduceMotion ? 1 : 0
                Behavior on opacity {
                    enabled: !shell.reduceMotion
                    NumberAnimation { duration: 180; easing.type: Easing.OutCubic }
                }
                Component.onCompleted: opacity = 1
            }
            VideoOutput {
                id: videoOut
                anchors.fill: parent
                visible: shell.detailIsVideo && shell.previewSource.length > 0
            }
            Text {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.margins: 8
                visible: shell.previewNote.length > 0
                text: shell.previewNote
                color: "white"
                wrapMode: Text.WordWrap
                font.pixelSize: 11
                font.family: "Segoe UI Variable Text"
            }
            MediaPlayer {
                id: player
                videoOutput: videoOut
                audioOutput: previewAudio
                source: shell.previewSource.length > 0 ? shell.previewSource : ""
                onErrorOccurred: shell.notePreview("코덱 또는 스트리밍 제약으로 미리보기를 재생할 수 없습니다")
            }
            Connections {
                target: shell
                function onPreviewChanged() {
                    if (shell.previewPlaying)
                        player.play()
                    else
                        player.pause()
                }
            }
            AudioOutput {
                id: previewAudio
                muted: shell.previewMuted
            }
        }
        Row {
            visible: shell.detailIsVideo
            spacing: 8
            Rectangle {
                width: 64
                height: 26
                radius: 8
                color: playArea.containsMouse ? ink.hover : ink.field
                Text {
                    anchors.centerIn: parent
                    text: shell.previewPlaying ? "일시정지" : "재생"
                    color: ink.title
                    font.pixelSize: 11
                    font.family: "Segoe UI Variable Text"
                }
                MouseArea {
                    id: playArea
                    anchors.fill: parent
                    onClicked: shell.previewPlaying ? shell.pausePreview() : shell.playPreview()
                }
            }
            Rectangle {
                width: 64
                height: 26
                radius: 8
                color: muteArea.containsMouse ? ink.hover : ink.field
                Text {
                    anchors.centerIn: parent
                    text: shell.previewMuted ? "소리" : "음소거"
                    color: ink.title
                    font.pixelSize: 11
                    font.family: "Segoe UI Variable Text"
                }
                MouseArea {
                    id: muteArea
                    anchors.fill: parent
                    onClicked: shell.togglePreviewMute()
                }
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
            visible: shell.detailMeta.length > 0
            width: parent.width
            text: shell.detailMeta
            color: ink.muted
            font.pixelSize: 11
            font.family: "Segoe UI Variable Text"
            wrapMode: Text.WordWrap
        }
        Text {
            visible: shell.detailError.length > 0
            width: parent.width
            text: shell.detailError
            color: ink.muted
            font.pixelSize: 11
            font.family: "Segoe UI Variable Text"
            wrapMode: Text.WordWrap
        }
        Column {
            visible: shell.formatChoices.length > 0
            width: parent.width
            spacing: 4
            Text {
                text: "형식 선택"
                color: ink.muted
                font.pixelSize: 11
                font.family: "Segoe UI Variable Text"
            }
            Repeater {
                model: shell.formatChoices
                delegate: Text {
                    required property int index
                    required property string modelData
                    readonly property var parts: modelData.split("|")
                    text: (parts[2] === "1" ? "● " : "○ ") + parts[1]
                    color: parts[2] === "1" ? ink.title : ink.muted
                    font.pixelSize: 11
                    font.family: "Segoe UI Variable Text"
                    width: 258
                    elide: Text.ElideRight
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: shell.selectFormat(parts[0])
                    }
                }
            }
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
