package risk.monitoring.user.verify.data.policy_0347

# Auto-generated policy 347 (Rego v1 syntax)
# Package: risk.monitoring.user.verify.data

# Metadata
metadata := {
    "policy_id": "0347",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0347_allowed if {
    input.user.active
    input.resource.public
}
policy_0347_allowed if {
    input.user.role == "admin"
}
default policy_0347_allowed = false
