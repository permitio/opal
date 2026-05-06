package risk.monitoring.user.verify.policy_0624

# Auto-generated policy 624 (Rego v1 syntax)
# Package: risk.monitoring.user.verify

# Metadata
metadata := {
    "policy_id": "0624",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0624_allowed = false
policy_0624_allowed if {
    input.user.active
    input.resource.public
}
