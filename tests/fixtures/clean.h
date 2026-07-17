#pragma once
#include <string>

namespace net {

class HttpClient {
public:
    class Options {          // nested config type — allowed
        int timeout_ms = 30000;
    };
    void get(const std::string& url);
};

class HttpError : public std::exception {  // coupled exception — exempt by default
public:
    const char* what() const noexcept override;
};

}  // namespace net
