package access.authentication.policy.verify.policy_0796

# Auto-generated policy 796 (Rego v1 syntax)
# Package: access.authentication.policy.verify

# Metadata
metadata := {
    "policy_id": "0796",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0796_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0796_allowed = false
