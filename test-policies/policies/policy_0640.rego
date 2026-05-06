package risk.enforcement.user.deny.helpers.policy_0640

# Auto-generated policy 640 (Rego v1 syntax)
# Package: risk.enforcement.user.deny.helpers

# Metadata
metadata := {
    "policy_id": "0640",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0640_allowed if {
    input.user.role == "admin"
}
default policy_0640_allowed = false
policy_0640_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
