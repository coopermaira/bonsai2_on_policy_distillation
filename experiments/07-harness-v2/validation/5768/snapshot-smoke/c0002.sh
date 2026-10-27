test "$PWD" = /app/persist && test "$CHECKPOINT_PROBE" = retained && test "$(cat counter)" = once && printf resumed > result
