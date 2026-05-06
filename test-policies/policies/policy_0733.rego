package compliance.monitoring.user.deny.policy_0733

# Auto-generated policy 733 (Rego v1 syntax)
# Package: compliance.monitoring.user.deny

# Metadata
metadata := {
    "policy_id": "0733",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0733_allowed if {
    input.user.active
    input.resource.public
}
default policy_0733_allowed = false
