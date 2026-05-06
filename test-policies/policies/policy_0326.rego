package compliance.monitoring.resource.verify.policy_0326

# Auto-generated policy 326 (Rego v1 syntax)
# Package: compliance.monitoring.resource.verify

# Metadata
metadata := {
    "policy_id": "0326",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0326_allowed if {
    data.policies.compliance.enabled
}
policy_0326_allowed if {
    input.user.role == "admin"
}
