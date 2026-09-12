Release notes, build 4.2.

This build adds a flag to override the default retry policy. Operators are
instructed to review the change before enabling it in production. The system
now logs the source of each override.

No schema changes are included. Roll back is supported by restoring the prior
snapshot.
