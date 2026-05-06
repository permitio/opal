package risk.authentication.user.allow.policy_0923

# Auto-generated policy 923 (Rego v1 syntax)
# Package: risk.authentication.user.allow

# Metadata
metadata := {
    "policy_id": "0923",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0923_allowed = false
policy_0923_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
