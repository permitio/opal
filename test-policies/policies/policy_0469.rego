package risk.authentication.user.check.policy_0469

# Auto-generated policy 469 (Rego v1 syntax)
# Package: risk.authentication.user.check

# Metadata
metadata := {
    "policy_id": "0469",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0469_allowed = false
policy_0469_allowed if {
    input.user.role == "admin"
}
