package access.monitoring.user.verify.policy_0363

# Auto-generated policy 363 (Rego v1 syntax)
# Package: access.monitoring.user.verify

# Metadata
metadata := {
    "policy_id": "0363",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0363_allowed = false
policy_0363_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
