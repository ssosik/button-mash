#ifndef Protocol_h
#define Protocol_h

// ---------------------------------------------------------------------------
// Wire protocol between the Teensy (controller) and the Matrix Portal
// (display).
//
// Framing: every message is '#', a verb, an optional ':' argument list, then
// '\n'. The receiver buffers until it sees '\n' and only then dispatches, so a
// message split across two reads is reassembled rather than dropped. The
// original code compared whole read chunks with startswith() and lost any
// message that straddled a 32-byte boundary.
//
// Anything changed here must be changed in display/code.py's HANDLERS table.
// ---------------------------------------------------------------------------

namespace protocol {

constexpr char kTerminator = '\n';

// Controller -> display
constexpr const char kConReady[] = "#CONREADY";
constexpr const char kNewGame[] = "#NEWGAME";
constexpr const char kShowSplash[] = "#SHOWSPLASH";
constexpr const char kShowHighScore[] = "#SHOWHIGHSCORE";
constexpr const char kShowPressStart[] = "#SHOWPRESSSTART";
constexpr const char kIsP1Ready[] = "#ISP1READY";
constexpr const char kIsP2Ready[] = "#ISP2READY";
constexpr const char kCountdownReady[] = "#GAMEREADY:READY";
constexpr const char kCountdownSet[] = "#GAMEREADY:SET";
constexpr const char kCountdownGo[] = "#GAMEREADY:GO";

// Take a trailing score argument.
constexpr const char kPlayer1Win[] = "#PLAYER1WIN:";
constexpr const char kPlayer2Win[] = "#PLAYER2WIN:";
constexpr const char kTieGame[] = "#TIEGAME:";

// Live score: "#SCORE:<p1>:<p2>"
constexpr const char kScore[] = "#SCORE:";

// Debug mode banner: "#DEBUG:<text>"
constexpr const char kDebug[] = "#DEBUG:";

// Names the next mode of the medley, between segments: "#MODE:<banner>"
constexpr const char kMode[] = "#MODE:";

// The colour each player is being asked for, as six hex digits, or "-" when
// the mode has no target. The display draws that player's score in it:
// "#TARGET:<p1>:<p2>"
constexpr const char kTarget[] = "#TARGET:";

// Display -> controller
constexpr const char kDisplayReady[] = "#DSPREADY";

} // namespace protocol

#endif
