package security.enforcement.user.verify.policy_0863

# Auto-generated policy 863 (Rego v1 syntax)
# Package: security.enforcement.user.verify

# Metadata
metadata := {
    "policy_id": "0863",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0863_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0863_allowed = false
policy_0863_allowed if {
    input.user.role == "admin"
}
