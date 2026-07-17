#pragma once
// A constants header: several small related enums, no state anywhere.
enum class Color { Red, Green, Blue };

typedef enum {
    ALPHA_ONE,
    ALPHA_TWO,
    ALPHA_THREE
} AlphaMode;

enum Status {
    STATUS_OK,
    STATUS_FAIL
};
