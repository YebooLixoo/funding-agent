import { Link } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { Navigate } from 'react-router-dom'

export default function Landing() {
  const { user, loading } = useAuth()

  if (loading) return null
  if (user) return <Navigate to="/dashboard" />

  return (
    <div className="min-h-screen bg-gradient-to-br from-brand-900 via-blue-800 to-blue-600 flex flex-col">
      <nav className="flex items-center justify-between px-8 py-6">
        <span className="text-2xl font-bold text-white tracking-tight">Funding Agent</span>
        <div className="flex gap-3">
          <Link
            to="/login"
            className="px-4 py-2 text-sm font-medium text-white hover:text-blue-200 transition-colors"
          >
            Log in
          </Link>
          <Link
            to="/register"
            className="px-4 py-2 text-sm font-medium bg-white text-brand-900 rounded-lg hover:bg-blue-50 transition-colors"
          >
            Get started
          </Link>
        </div>
      </nav>

      <div className="flex-1 flex items-center justify-center px-4">
        <div className="max-w-3xl text-center">
          <h1 className="text-5xl sm:text-6xl font-extrabold text-white leading-tight mb-6">
            Your personalized<br />funding discovery agent
          </h1>
          <p className="text-xl text-blue-100 mb-10 max-w-2xl mx-auto">
            Upload your resume, and we'll automatically find relevant funding opportunities
            from 25+ sources — NSF, NIH, DOE, industry fellowships, and more.
            Personalized scoring, deadline alerts, and weekly digests.
          </p>
          <div className="flex gap-4 justify-center">
            <Link
              to="/register"
              className="px-8 py-3 text-lg font-semibold bg-white text-brand-900 rounded-lg hover:bg-blue-50 transition-colors shadow-lg"
            >
              Create free account
            </Link>
            <a
              href="#features"
              className="px-8 py-3 text-lg font-semibold text-white border-2 border-white/30 rounded-lg hover:bg-white/10 transition-colors"
            >
              Learn more
            </a>
          </div>
        </div>
      </div>

      <div id="features" className="bg-white py-20 px-4">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-3xl font-bold text-center text-gray-900 mb-12">
            How it works
          </h2>
          <div className="grid md:grid-cols-3 gap-8">
            {[
              {
                step: '1',
                title: 'Upload your CV',
                desc: 'We extract your research keywords automatically using AI.',
              },
              {
                step: '2',
                title: 'Get matched',
                desc: 'Our scoring algorithm finds the most relevant funding opportunities for your profile.',
              },
              {
                step: '3',
                title: 'Stay updated',
                desc: 'Receive personalized email digests with new opportunities and deadline alerts.',
              },
            ].map((item) => (
              <div key={item.step} className="text-center">
                <div className="w-12 h-12 bg-brand-600 text-white rounded-full flex items-center justify-center text-xl font-bold mx-auto mb-4">
                  {item.step}
                </div>
                <h3 className="text-lg font-semibold text-gray-900 mb-2">{item.title}</h3>
                <p className="text-gray-600">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
