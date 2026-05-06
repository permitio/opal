package compliance.monitoring.resource.check.policy_0463

# Auto-generated policy 463 (Rego v1 syntax)
# Package: compliance.monitoring.resource.check

# Metadata
metadata := {
    "policy_id": "0463",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0463_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0463_allowed if {
    data.policies.compliance.enabled
}
policy_0463_allowed if {
    input.user.active
    input.resource.public
}
