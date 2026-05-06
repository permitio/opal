package compliance.authorization.resource.verify.policy_0858

# Auto-generated policy 858 (Rego v1 syntax)
# Package: compliance.authorization.resource.verify

# Metadata
metadata := {
    "policy_id": "0858",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0858_allowed if {
    input.user.role == "admin"
}
policy_0858_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0858_allowed if {
    input.user.active
    input.resource.public
}
policy_0858_allowed if {
    data.policies.compliance.enabled
}
