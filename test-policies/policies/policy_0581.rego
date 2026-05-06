package audit.enforcement.user.allow.policy_0581

# Auto-generated policy 581 (Rego v1 syntax)
# Package: audit.enforcement.user.allow

# Metadata
metadata := {
    "policy_id": "0581",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0581_allowed = false
policy_0581_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
