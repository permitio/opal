package access.monitoring.user.verify.policy_0501

# Auto-generated policy 501 (Rego v1 syntax)
# Package: access.monitoring.user.verify

# Metadata
metadata := {
    "policy_id": "0501",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0501_allowed if {
    input.user.role == "admin"
}
default policy_0501_allowed = false
