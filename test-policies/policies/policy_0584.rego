package compliance.monitoring.user.validate.policy_0584

# Auto-generated policy 584 (Rego v1 syntax)
# Package: compliance.monitoring.user.validate

# Metadata
metadata := {
    "policy_id": "0584",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0584_allowed if {
    data.policies.compliance.enabled
}
policy_0584_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0584_allowed if {
    input.user.active
    input.resource.public
}
