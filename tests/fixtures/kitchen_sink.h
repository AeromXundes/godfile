#pragma once
#include <string>
#include <stdexcept>

class Widget;                       // forward decl — must NOT count
struct Gadget;                      // forward decl — must NOT count

class Mutex {                       // real def — counts
public:
    class ScopedLock {              // nested — must NOT count
    public:
        explicit ScopedLock(Mutex& m);
    };
    void lock();
};

struct SocketAddress {              // real def — counts
    std::string host;
    int port;
};

enum class LogLevel { Debug, Info, Warn };  // counts

union Value {                       // counts
    int i;
    double d;
};

template <typename T>
class RingBuffer {                  // template def — counts
    T* data_;
};

template <>
class RingBuffer<bool> {            // specialization — should NOT double-count
    void* bits_;
};

class ParseError : public std::runtime_error {  // exception type — exception-heuristic
public:
    using std::runtime_error::runtime_error;
};

typedef struct {                    // anonymous struct via typedef
    int x, y;
} Point;

using StringMap = int;              // alias — configurable, default not counted

namespace detail {
    class InternalHelper {          // detail namespace — internal helper heuristic
        int state_;
    };
}

namespace app {
    class Service {                 // namespaced top-level def — counts
        void start();
    };
}

inline std::string to_hex(int v);   // free function — not a type
