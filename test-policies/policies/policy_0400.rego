package compliance.authorization.context.allow.policy_0400

# Auto-generated policy 400 (Rego v1 syntax)
# Package: compliance.authorization.context.allow

# Metadata
metadata := {
    "policy_id": "0400",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0400_allowed if {
    input.user.role == "admin"
}
policy_0400_allowed if {
    data.policies.compliance.enabled
}
policy_0400_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0400_allowed if {
    input.user.active
    input.resource.public
}
