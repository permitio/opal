package governance.validation.user.check.policy_0800

# Auto-generated policy 800 (Rego v1 syntax)
# Package: governance.validation.user.check

# Metadata
metadata := {
    "policy_id": "0800",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0800_allowed if {
    input.user.role == "admin"
}
default policy_0800_allowed = false
