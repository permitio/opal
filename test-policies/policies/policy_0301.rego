package audit.authentication.policy.deny.policy_0301

# Auto-generated policy 301 (Rego v1 syntax)
# Package: audit.authentication.policy.deny

# Metadata
metadata := {
    "policy_id": "0301",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0301_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0301_allowed = false
