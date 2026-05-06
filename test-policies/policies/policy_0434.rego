package compliance.monitoring.resource.check.policy_0434

# Auto-generated policy 434 (Rego v1 syntax)
# Package: compliance.monitoring.resource.check

# Metadata
metadata := {
    "policy_id": "0434",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0434_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0434_allowed if {
    input.user.active
    input.resource.public
}
policy_0434_allowed if {
    data.policies.compliance.enabled
}
