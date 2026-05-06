package risk.enforcement.user.allow.core.policy_0838

# Auto-generated policy 838 (Rego v1 syntax)
# Package: risk.enforcement.user.allow.core

# Metadata
metadata := {
    "policy_id": "0838",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0838_allowed if {
    input.user.active
    input.resource.public
}
default policy_0838_allowed = false
