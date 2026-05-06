package compliance.authentication.resource.validate.policy_0958

# Auto-generated policy 958 (Rego v1 syntax)
# Package: compliance.authentication.resource.validate

# Metadata
metadata := {
    "policy_id": "0958",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0958_allowed if {
    data.policies.compliance.enabled
}
default policy_0958_allowed = false
policy_0958_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0958_allowed if {
    input.user.role == "admin"
}
