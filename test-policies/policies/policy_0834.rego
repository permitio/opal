package security.authentication.user.verify.logic.policy_0834

# Auto-generated policy 834 (Rego v1 syntax)
# Package: security.authentication.user.verify.logic

# Metadata
metadata := {
    "policy_id": "0834",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0834_allowed = false
policy_0834_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
